"""
Publish Image Manager launcher rows to EDA app status (.cluster.apps.imagemanager.status).

Cable-map writes dashboard rows via EDK gRPC to the state aggregator; CR-based EQL
does not work here because CE ignores our cluster-scoped CRDs (InvalidNamespaceOrGvk)
and nested ImageManagerConfig.status.artifacts arrays are not flat-table queryable.

This module shells out to the bundled Go status-publisher binary (mTLS to eda-aggsvr).
"""

import json
import logging
import os
import subprocess
import threading
from urllib.parse import quote

logger = logging.getLogger("app_status")

_PUBLISHER = os.environ.get(
    "STATUS_PUBLISHER_BIN",
    os.path.join(os.path.dirname(__file__), "status-publisher"),
)
_STATUS_BASE = ".cluster.apps.imagemanager.status"   # per-image rows
_APP_BASE = ".cluster.apps.imagemanager.app"          # single service/server row
_HTTPPROXY_PATH = "/core/httpproxy/v1/imagemanager/"
_SERVICE_LABEL = "Image Manager"
APP_VERSION = [""]   # set by main at startup; shown in the dashboard app table
_last_known_ids = set()
_last_synced = [None]   # last successfully-synced desired dict (skip no-op sends)
_purged_stale = [False]  # first sync of this process wipes rows from prior installs
_sync_lock = threading.Lock()


def _row_id(row):
    ns = row.get("namespace") or "default"
    name = row.get("name") or row.get("uploadId") or ""
    safe_ns = "".join(c if c.isalnum() or c in ".-" else "-" for c in ns.lower()).strip("-") or "default"
    safe_name = "".join(c if c.isalnum() or c in ".-" else "-" for c in name.lower()).strip("-") or "unknown"
    return f"{safe_ns}--{safe_name}"[:253]


def _http_state():
    try:
        import fileserver
        return fileserver.server_state()
    except Exception:  # noqa: BLE001
        return ""


def _app_row(tracked_rows, health, http_state):
    """The single row of the `.app` table (cable-map parity: data=Ready,
    http=Reachable). Always present, so the dashboard shows the app is
    installed + live even with zero images."""
    counts = {}
    for row in tracked_rows:
        s = row.get("downloadStatus") or "Unknown"
        counts[s] = counts.get(s, 0) + 1
    agg = ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) if counts else "no images"
    n = len(tracked_rows)
    version = APP_VERSION[0] or ""
    details = "\n".join([
        "app: Image Manager",
        f"version: {version}",
        f"health: {health}",
        f"ui: {http_state}",
        f"images: {n}" + (f" ({agg})" if counts else ""),
        f"namespace: {os.environ.get('POD_NAMESPACE', 'eda-system')}",
        f"url: {_HTTPPROXY_PATH}",
    ])
    return {
        "path": _APP_BASE,
        "id": "imagemanager",
        "service": _SERVICE_LABEL,
        "health": health,
        "http": http_state,
        "version": version,
        "image": f"{n} image(s)",
        "namespace": os.environ.get("POD_NAMESPACE", "eda-system"),
        "status": agg,
        "open": "View",
        "url": _HTTPPROXY_PATH,
        "details": details,
    }


def sync_app_status_rows(tracked_rows, health=None):
    """Sync both launcher tables:

      .cluster.apps.imagemanager.app     -> one service/server row
      .cluster.apps.imagemanager.status  -> one row per tracked image

    No-op (no publisher spawn, no gRPC traffic) when nothing changed since the
    last successful sync, so callers can invoke this at a high frequency.
    """
    if not os.path.isfile(_PUBLISHER):
        logger.debug("status-publisher binary missing at %s; skipping app status sync", _PUBLISHER)
        return

    if health is None:
        bad = [r for r in tracked_rows
               if r.get("downloadStatus") in ("Error", "Failed")]
        health = "Degraded" if bad else "Ready"
    http_state = _http_state()

    desired = {"app": _app_row(tracked_rows, health, http_state)}
    for row in tracked_rows:
        rid = _row_id(row)
        display = row.get("displayName") or row.get("name") or rid
        upload_id = row.get("uploadId") or row.get("name") or ""
        # Per-row deep link: clicking the dashboard row opens the app with the
        # NodeProfile/details dialog for this image already open.
        deep_link = _HTTPPROXY_PATH + (
            f"?details={quote(upload_id, safe='')}" if upload_id else "")
        desired[rid] = {
            "path": _STATUS_BASE,
            "id": rid,
            "image": display,
            "namespace": row.get("namespace") or "",
            "status": row.get("downloadStatus") or row.get("health") or "",
            "open": "View",
            "url": deep_link,
            # Shown in the dashlet info panel when a row is clicked (cable-map
            # hidden-details pattern): the ready-to-paste NodeProfile YAML.
            "details": row.get("nodeProfileExample") or row.get("snippet") or "",
        }

    with _sync_lock:
        global _last_known_ids
        if desired == _last_synced[0] and _purged_stale[0]:
            return
        deletes = []
        if not _purged_stale[0]:
            # Rows survive in the EDA state DB across app restarts/reinstalls;
            # wipe both tables once per process so orphans from a previous
            # install (possibly with a deleted PVC) never linger.
            deletes.append(_STATUS_BASE)
            deletes.append(_APP_BASE)
        deletes.extend(
            f'{_STATUS_BASE}{{.id=="{rid}"}}'
            for rid in sorted(_last_known_ids - set(desired))
            if rid != "app"
        )
        payload = {
            "adds": list(desired.values()),
            "deletes": deletes,
        }

        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            proc = subprocess.run(
                [_PUBLISHER],
                input=data,
                capture_output=True,
                timeout=25,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            logger.warning("app status sync failed: %s", e)
            return
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
            logger.warning("app status sync failed (exit %d): %s", proc.returncode, err[:500])
            return
        _last_known_ids = set(desired)
        _last_synced[0] = desired
        _purged_stale[0] = True
        logger.info("app status sync: %d row(s)", len(desired))
