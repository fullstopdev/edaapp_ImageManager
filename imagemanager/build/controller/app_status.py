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
_sync_lock = threading.Lock()


def _row_id(row):
    ns = row.get("namespace") or "default"
    name = row.get("name") or row.get("uploadId") or ""
    safe_ns = "".join(c if c.isalnum() or c in ".-" else "-" for c in ns.lower()).strip("-") or "default"
    safe_name = "".join(c if c.isalnum() or c in ".-" else "-" for c in name.lower()).strip("-") or "unknown"
    return f"{safe_ns}--{safe_name}"[:253]


def sync_app_status_rows(tracked_rows):
    """Upsert/delete .cluster.apps.imagemanager.status rows for launcher EQL.

    No-op (no publisher spawn, no gRPC traffic) when nothing changed since the
    last successful sync, so callers can invoke this at a high frequency.
    """
    if not os.path.isfile(_PUBLISHER):
        logger.debug("status-publisher binary missing at %s; skipping app status sync", _PUBLISHER)
        return

    desired = {}
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
            "image": display,
            "namespace": row.get("namespace") or "",
            "status": row.get("downloadStatus") or row.get("health") or "",
            "open": "View",
            "url": deep_link,
        }

    with _sync_lock:
        global _last_known_ids
        if desired == _last_synced[0]:
            return
        payload = {
            "adds": list(desired.values()),
            "deletes": [
                f'{_STATUS_BASE}{{.id=="{rid}"}}'
                for rid in sorted(_last_known_ids - set(desired))
            ],
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
        logger.info("app status sync: %d row(s)", len(desired))
