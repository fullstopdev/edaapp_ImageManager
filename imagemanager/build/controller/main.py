"""
EDA Image Manager controller - entry point.

Long-running controller that:
  * serves an upload web UI + an in-cluster file-serve endpoint (fileserver.py),
  * on upload, stores the file on the PVC and creates an Artifact CR pointing
    eda-asvr back at this app to pull + re-host the file,
  * reconciles every RECONCILE_INTERVAL: mirrors each Artifact's download status
    into ImageManagerConfig.status for the UI and computes storage stats.

This app is the DURABLE origin eda-asvr pulls from: eda-asvr keeps no persistent
store of its own (its re-hosted copy lives on ephemeral pod storage) and
re-pulls from us whenever its pod restarts. So an uploaded file is retained for
the life of its Artifact and is never auto-purged -- it is removed only when the
user deletes the Artifact (see fileserver._handle_delete).

Artifact/status operations use the Kubernetes API (pod ServiceAccount token);
the web UI sign-in is handled separately in auth.py (EDA OIDC / Keycloak).
"""

import hashlib
import json
import logging
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone

import app_status
import artifact_launcher
import fileserver
import imports
import k8s
import uploads

VERSION = "v0.0.11"
UPLOAD_DIR = "/data/uploads"
TLS_CRT = "/var/run/eda/tls/serving/tls.crt"
PORT = 8443
RECONCILE_INTERVAL = int(os.environ.get("RECONCILE_INTERVAL", "60"))
STARTUP_DELAY_SECONDS = int(os.environ.get("STARTUP_DELAY_SECONDS", "45"))
LAUNCHER_SYNC_GRACE_SECONDS = int(os.environ.get("LAUNCHER_SYNC_GRACE_SECONDS", "0"))
_MAX_RECONCILE_BACKOFF = int(os.environ.get("MAX_RECONCILE_BACKOFF", "300"))

CRD_GROUP = "imagemanager.eda.edacommunity.com"
CRD_VERSION = "v1alpha1"
CRD_PLURAL = "imagemanagerconfigs"
CRD_KIND = "ImageManagerConfig"
CRD_NAME = "default"

DEFAULTS = {
    "defaultArtifactNamespace": "eda",
    "defaultRepo": "images",
    "maxUploadMiB": 4096,
    "filePullBaseUrl": "",
}

logger = logging.getLogger("main")
shutdown_event = threading.Event()
_last_status_hash = None
_import_lock = threading.Lock()
_import_running = False
_startup_monotonic = time.monotonic()
_consecutive_reconcile_errors = 0
_status_daemon_proc = None


def _start_status_publisher_daemon():
    """Start persistent status-publisher daemon (EDK dbStream parity)."""
    global _status_daemon_proc
    publisher = os.environ.get(
        "STATUS_PUBLISHER_BIN",
        os.path.join(os.path.dirname(__file__), "status-publisher"),
    )
    if not os.path.isfile(publisher):
        logger.debug("status-publisher binary missing at %s", publisher)
        return
    try:
        _status_daemon_proc = subprocess.Popen(
            [publisher, "daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.5)
        if _status_daemon_proc.poll() is not None:
            err = (_status_daemon_proc.stderr.read() or b"").decode("utf-8", errors="replace")
            if err.strip():
                logger.warning("status-publisher daemon stderr: %s", err[:500])
            logger.warning("status-publisher daemon exited early (code %s)", _status_daemon_proc.returncode)
            _status_daemon_proc = None
            return
        logger.info("status-publisher daemon started (pid %d)", _status_daemon_proc.pid)
    except OSError as e:
        logger.warning("failed to start status-publisher daemon: %s", e)


def _stop_status_publisher_daemon():
    global _status_daemon_proc
    if _status_daemon_proc and _status_daemon_proc.poll() is None:
        _status_daemon_proc.terminate()
        try:
            _status_daemon_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _status_daemon_proc.kill()
    _status_daemon_proc = None


def _setup_logging():
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    fmt.converter = time.gmtime
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


def _signal_handler(signum, frame):
    logger.info("Received signal %d, initiating shutdown", signum)
    shutdown_event.set()


def _wait_for_cert(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.isfile(TLS_CRT):
            return True
        if shutdown_event.wait(1):
            return False
    return False


def _read_config():
    """Read ImageManagerConfig/default spec, merged over DEFAULTS."""
    cfg = dict(DEFAULTS)
    try:
        cr = k8s.read_cr(CRD_GROUP, CRD_VERSION, CRD_PLURAL, CRD_NAME)
        if cr:
            spec = cr.get("spec", {}) or {}
            for key in DEFAULTS:
                if spec.get(key) not in (None, ""):
                    cfg[key] = spec[key]
    except Exception as e:
        logger.warning("Failed to read %s/%s: %s", CRD_KIND, CRD_NAME, e)
    # clamp
    cfg["maxUploadMiB"] = max(1, min(65536, int(cfg["maxUploadMiB"])))
    return cfg


def _ensure_default_cr():
    try:
        if k8s.read_cr(CRD_GROUP, CRD_VERSION, CRD_PLURAL, CRD_NAME):
            return
        spec = {k: v for k, v in DEFAULTS.items() if v not in (None, "")}
        body = {
            "apiVersion": f"{CRD_GROUP}/{CRD_VERSION}",
            "kind": CRD_KIND,
            "metadata": {"name": CRD_NAME},
            "spec": spec,
        }
        k8s.create_cr(CRD_GROUP, CRD_VERSION, CRD_PLURAL, body)
        logger.info("Created default %s CR", CRD_KIND)
    except Exception as e:
        logger.warning("Failed to ensure default %s: %s", CRD_KIND, e)


def _status_payload(health, message, tracked):
    count, total_bytes = uploads.storage_stats()
    return {
        "health": health,
        "message": message,
        "open": "View",
        "lastReconcileTime": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "uploadsStored": count,
        "bytesStored": total_bytes,
        "artifacts": [
            {
                "name": t.get("name", ""),
                "displayName": t.get("displayName") or t.get("name", ""),
                "namespace": t.get("namespace", ""),
                "repo": t.get("repo", ""),
                "filePath": t.get("filePath", ""),
                "sizeBytes": t.get("sizeBytes"),
                "downloadStatus": t.get("downloadStatus", ""),
                "statusReason": t.get("statusReason", ""),
                "externalUrl": t.get("externalUrl", ""),
                "open": "View",
            }
            for t in tracked[:500]
        ],
        "version": VERSION,
    }


def _update_status(health, message, tracked):
    global _last_status_hash
    try:
        cr = k8s.read_cr(CRD_GROUP, CRD_VERSION, CRD_PLURAL, CRD_NAME)
        if not cr:
            return
        status = _status_payload(health, message, tracked)
        digest = hashlib.sha256(
            json.dumps(status, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if digest == _last_status_hash:
            return
        cr["status"] = status
        k8s.update_cr_status(CRD_GROUP, CRD_VERSION, CRD_PLURAL, CRD_NAME, cr)
        _last_status_hash = digest
    except Exception as e:
        logger.warning("Failed to update CRD status: %s", e)


def _run_imports_async(cfg):
    """Run URL imports off the main reconcile path so uploads stay responsive."""
    global _import_running
    with _import_lock:
        if _import_running:
            return
        _import_running = True

    def _work():
        global _import_running
        try:
            imports.reconcile(cfg)
        except Exception as e:  # noqa: BLE001
            logger.warning("ImageImport reconcile failed: %s", e)
        finally:
            with _import_lock:
                _import_running = False

    threading.Thread(target=_work, daemon=True, name="imports").start()


def main():
    _setup_logging()
    logger.info("Image Manager controller started (version %s)", VERSION)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    if not os.path.isfile(TLS_CRT) and not _wait_for_cert(timeout=30):
        logger.error("Serving cert %s not present after 30s; server will fall back "
                     "to HTTP (probes/pulls will fail until cert mounts)", TLS_CRT)
    fileserver.set_config(_read_config())
    fileserver.start_file_server(PORT)
    fileserver.write_healthz("starting", None)
    _start_status_publisher_daemon()

    _ensure_default_cr()

    if STARTUP_DELAY_SECONDS > 0:
        logger.info("Deferring first reconcile for %ds so EDA install can settle",
                    STARTUP_DELAY_SECONDS)
        if shutdown_event.wait(timeout=STARTUP_DELAY_SECONDS):
            logger.info("Controller shutting down during startup delay")
            fileserver.stop_file_server()
            _stop_status_publisher_daemon()
            return

    while not shutdown_event.is_set():
        cycle_start = time.time()
        cfg = _read_config()
        fileserver.set_config(cfg)

        health, message = "ok", "All systems operational"
        tracked = []
        reconcile_failed = False
        global _consecutive_reconcile_errors
        try:
            tracked = fileserver.build_tracked_list()
            bad = [t for t in tracked if t.get("downloadStatus") in ("Error", "Failed")]
            if bad:
                health = "degraded"
                message = f"{len(bad)} artifact(s) reported Error/Failed by eda-asvr"
            _consecutive_reconcile_errors = 0
        except Exception as e:
            reconcile_failed = True
            _consecutive_reconcile_errors += 1
            health, message = "degraded", f"reconcile error: {e}"
            logger.warning("Reconcile listing failed: %s", e)

        now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fileserver.write_healthz(health, now_str)
        _update_status(health, message, tracked)
        try:
            artifact_launcher.sync_launcher_rows(
                tracked,
                startup_monotonic=_startup_monotonic,
                grace_seconds=LAUNCHER_SYNC_GRACE_SECONDS,
            )
        except Exception as e:
            logger.warning("Launcher artifact sync failed: %s", e)
        try:
            app_status.sync_app_status_rows(tracked)
        except Exception as e:
            logger.warning("App status sync failed: %s", e)

        _run_imports_async(cfg)

        logger.info("Reconcile done: %d tracked upload(s), health=%s (%dms)",
                    len(tracked), health, int((time.time() - cycle_start) * 1000))
        wait = RECONCILE_INTERVAL
        if reconcile_failed:
            wait = min(
                RECONCILE_INTERVAL * (2 ** min(_consecutive_reconcile_errors - 1, 4)),
                _MAX_RECONCILE_BACKOFF,
            )
            logger.info("Backing off reconcile for %ds after error", wait)
        shutdown_event.wait(timeout=wait)

    logger.info("Controller shutting down")
    fileserver.stop_file_server()
    _stop_status_publisher_daemon()


if __name__ == "__main__":
    main()
