"""
Publish Image Manager launcher rows to the EDA state DB
(.cluster.apps.imagemanager.{app,status}) via the status-publisher daemon.

Cable-map writes dashboard rows via EDK gRPC to the state aggregator; CR-based EQL
does not work here because CE ignores our cluster-scoped CRDs (InvalidNamespaceOrGvk)
and nested ImageManagerConfig.status.artifacts arrays are not flat-table queryable.

The Go daemon owns the aggregator stream AND the desired row set: state DB rows
are ephemeral (the aggregator purges them whenever the publishing stream ends),
so the daemon replays everything on each reconnect. This module just hands the
daemon the full desired row set over its unix socket whenever anything changed.
"""

import json
import logging
import os
import socket
import threading
from urllib.parse import quote

logger = logging.getLogger("app_status")

_SOCKET = os.environ.get("STATUS_PUBLISHER_SOCKET", "/tmp/imagemanager-status.sock")
_STATUS_BASE = ".cluster.apps.imagemanager.status"   # per-image rows
_APP_BASE = ".cluster.apps.imagemanager.app"          # single service/server row
_HTTPPROXY_PATH = "/core/httpproxy/v1/imagemanager"
_SERVICE_LABEL = "Image Manager"
APP_VERSION = [""]   # set by main at startup; shown in the dashboard app table
_last_synced = [None]   # last successfully-synced desired dict (skip no-op sends)
_sync_lock = threading.Lock()


def reset_publisher_state():
    """Forget the last-synced snapshot. Called when the daemon is (re)started:
    a new daemon process has an empty desired-set cache, so the next sync must
    push the full state even if our rows did not change."""
    with _sync_lock:
        _last_synced[0] = None


def _send_to_daemon(data):
    """Write one payload to the daemon socket, wait for OK/ERR. Raises on error."""
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(12)
    try:
        conn.connect(_SOCKET)
        conn.sendall(data)
        conn.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            b = conn.recv(4096)
            if not b:
                break
            chunks.append(b)
        resp = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if resp and not resp.startswith("OK"):
            raise RuntimeError(resp[:500])
    finally:
        conn.close()


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

    No-op (no socket traffic) when nothing changed since the last successful
    sync, so callers can invoke this at a high frequency.
    """
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
            f"?details={quote(upload_id, safe='')}" if upload_id else "/")
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
        if desired == _last_synced[0]:
            return
        # The payload is always the FULL desired row set; the daemon diffs it
        # against what it already published on the current stream (issuing
        # per-row predicate deletes for removed ids) and replays everything
        # after a stream/daemon restart, because the aggregator purges all
        # rows when the publishing stream ends.
        payload = {"adds": list(desired.values())}
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            _send_to_daemon(data)
        except (OSError, RuntimeError) as e:
            logger.warning("app status sync failed: %s", e)
            return
        _last_synced[0] = desired
        logger.info("app status sync: %d row(s)", len(desired))
