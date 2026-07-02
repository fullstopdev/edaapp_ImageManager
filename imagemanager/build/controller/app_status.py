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
_STATUS_BASE = ".cluster.apps.imagemanager.status"
_HTTPPROXY_PATH = "/core/httpproxy/v1/imagemanager/"
_SERVICE_LABEL = "Image Manager"
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


def _summary_row(tracked_rows, health, http_state):
    """Always-present service row (cable-map parity: data=Ready, http=Reachable).
    Guarantees the dashboard shows the app is installed + live even with zero
    images, and aggregates per-status counts."""
    counts = {}
    for row in tracked_rows:
        s = row.get("downloadStatus") or "Unknown"
        counts[s] = counts.get(s, 0) + 1
    agg = ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) if counts else "no images"
    n = len(tracked_rows)
    details = "\n".join([
        "app: Image Manager",
        f"health: {health}",
        f"ui: {http_state}",
        f"images: {n}" + (f" ({agg})" if counts else ""),
        f"namespace: {os.environ.get('POD_NAMESPACE', 'eda-system')}",
        f"url: {_HTTPPROXY_PATH}",
    ])
    return {
        "id": "imagemanager--app",
        "service": _SERVICE_LABEL,
        "health": health,
        "http": http_state,
        "image": f"{n} image(s)",
        "namespace": os.environ.get("POD_NAMESPACE", "eda-system"),
        "status": agg,
        "open": "View",
        "url": _HTTPPROXY_PATH,
        "details": details,
    }


def sync_app_status_rows(tracked_rows, health=None):
    """Upsert/delete .cluster.apps.imagemanager.status rows for launcher EQL.

    Publishes one service summary row (health/reachability, always present)
    plus one row per tracked image. No-op (no publisher spawn, no gRPC
    traffic) when nothing changed since the last successful sync, so callers
    can invoke this at a high frequency.
    """
    if not os.path.isfile(_PUBLISHER):
        logger.debug("status-publisher binary missing at %s; skipping app status sync", _PUBLISHER)
        return

    if health is None:
        bad = [r for r in tracked_rows
               if r.get("downloadStatus") in ("Error", "Failed")]
        health = "Degraded" if bad else "Ready"
    http_state = _http_state()

    desired = {}
    summary = _summary_row(tracked_rows, health, http_state)
    desired[summary["id"]] = summary
    for row in tracked_rows:
        rid = _row_id(row)
        display = row.get("displayName") or row.get("name") or rid
        upload_id = row.get("uploadId") or row.get("name") or ""
        # Per-row deep link: clicking the dashboard row opens the app with the
        # NodeProfile/details dialog for this image already open.
        deep_link = _HTTPPROXY_PATH + (
            f"?details={quote(upload_id, safe='')}" if upload_id else "")
        desired[rid] = {
            "id": rid,
            "service": _SERVICE_LABEL,
            "health": "",   # app-level columns live on the summary row
            "http": "",
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
            # wipe the whole table once per process so orphans from a previous
            # install (possibly with a deleted PVC) never linger.
            deletes.append(_STATUS_BASE)
        deletes.extend(
            f'{_STATUS_BASE}{{.id=="{rid}"}}'
            for rid in sorted(_last_known_ids - set(desired))
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
