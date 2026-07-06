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
import artifact
import artifact_launcher
import fileserver
import import_common
import imports
import k8s
import uploads

VERSION = "v0.0.52"
UPLOAD_DIR = "/data/uploads"
TLS_CRT = "/var/run/eda/tls/serving/tls.crt"
PORT = 8443
RECONCILE_INTERVAL = int(os.environ.get("RECONCILE_INTERVAL", "60"))
# Fast loop: rebuild artifact status + push dashboard rows every couple seconds
# (sync_app_status_rows is a no-op when nothing changed, so this is cheap).
STATUS_SYNC_INTERVAL = int(os.environ.get("STATUS_SYNC_INTERVAL", "2"))
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
# Set by the Artifact watch / UI handlers when something changed; the status
# sync loop wakes on it instantly instead of waiting out its poll interval.
sync_kick = threading.Event()
_last_status_hash = None
_import_lock = threading.Lock()
_import_running = False
_startup_monotonic = time.monotonic()
_consecutive_reconcile_errors = 0
_status_daemon_proc = None
_storage_reconcile_lock = threading.Lock()
_reconcile_cycle = 0


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
        # stderr inherited so daemon logs land in the pod log (a PIPE nobody
        # drains would eventually block the daemon on write).
        _status_daemon_proc = subprocess.Popen(
            [publisher, "daemon"],
            stdout=subprocess.DEVNULL,
        )
        time.sleep(0.5)
        if _status_daemon_proc.poll() is not None:
            logger.warning("status-publisher daemon exited early (code %s); "
                           "will retry from the status sync loop",
                           _status_daemon_proc.returncode)
            _status_daemon_proc = None
            return
        # A fresh daemon has an empty desired-set cache (and the aggregator
        # purged the old stream's rows) — force the next sync to resend all.
        app_status.reset_publisher_state()
        logger.info("status-publisher daemon started (pid %d)", _status_daemon_proc.pid)
    except OSError as e:
        logger.warning("failed to start status-publisher daemon: %s", e)
        _status_daemon_proc = None


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


def _maybe_delete_pvc_on_uninstall():
    """When the Deployment is being removed (app uninstall), drop PVC + managed CRs.

    Recreate upgrades only terminate the pod — the Deployment itself stays, so
    its deletionTimestamp is absent and the claim is kept.
    """
    ns = os.environ.get("POD_NAMESPACE", "eda-system")
    dep = os.environ.get("DEPLOYMENT_NAME", "eda-imagemanager")
    pvc = os.environ.get("PVC_NAME", "imagemanager-data")
    try:
        obj = k8s.read_namespaced_workload("apps/v1", "deployments", dep, ns)
        if not obj or not (obj.get("metadata") or {}).get("deletionTimestamp"):
            return
        logger.info("Deployment %s is deleting — removing managed Artifacts and PVC %s",
                    dep, pvc)
        try:
            artifact.delete_all_managed_artifacts()
        except Exception as e:  # noqa: BLE001
            logger.warning("Managed Artifact delete on uninstall failed: %s", e)
        k8s.delete_pvc(pvc, ns)
    except Exception as e:  # noqa: BLE001 — best-effort uninstall cleanup
        logger.warning("PVC delete on uninstall failed: %s", e)


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


def _artifact_watch_loop():
    """Event-driven dashboard sync (cable-map/EDK parity).

    EDK apps like cable-map never poll: the runtime streams CR changes to
    them and they publish state DB rows the moment something changes. Our
    stdlib equivalent is a cluster-wide K8s watch on the Artifact CRs this
    app manages — the API server pushes ADDED/MODIFIED/DELETED the instant
    eda-asvr updates a download status or a CR is created/removed (from the
    app, kubectl, anywhere). Each event drops the tracked-list cache and
    kicks the sync loop, so the dashboard reflects the change within ~a
    second instead of a poll interval. Each (re)connect replays current CRs
    as ADDED events, which doubles as anti-entropy after apiserver blips.
    """
    while not shutdown_event.is_set():
        try:
            k8s.watch_cr_all_namespaces(
                artifact.ARTIFACT_GROUP, artifact.ARTIFACT_VERSION,
                artifact.ARTIFACT_PLURAL,
                on_event=lambda etype, obj: (
                    fileserver.invalidate_tracked_cache(), sync_kick.set()),
                label_selector=f"{artifact.MANAGED_LABEL}=true",
                stop=shutdown_event,
            )
        except Exception as e:  # noqa: BLE001 - reconnect on any failure
            logger.debug("artifact watch interrupted: %s", e)
            shutdown_event.wait(timeout=3)


def _status_sync_loop():
    """Push artifact status to the EDA dashboard instantly.

    Sleeps on sync_kick: the Artifact watch and UI actions set it the moment
    anything changes, so a publish follows within ~0.5s. A STATUS_SYNC_INTERVAL
    timeout (default 2s) doubles as a safety resync — cheap, because the sync
    no-ops (no gRPC traffic) when rows are unchanged. Also (re)starts the
    status-publisher daemon whenever it isn't running (it would otherwise stay
    down until the pod restarts, freezing the dashboard).
    """
    while not shutdown_event.is_set():
        kicked = sync_kick.wait(timeout=max(1, STATUS_SYNC_INTERVAL))
        if shutdown_event.is_set():
            return
        if kicked:
            # Coalesce event bursts (multi-artifact uploads, watch replays)
            # into one rebuild, then clear so new events re-arm the kick.
            time.sleep(0.3)
            sync_kick.clear()
            fileserver.invalidate_tracked_cache()
        try:
            if _status_daemon_proc is None:
                # First start failed (eda-sa / TLS mounts not ready at pod
                # start); keep retrying so the dashboard doesn't stay frozen.
                _start_status_publisher_daemon()
            elif _status_daemon_proc.poll() is not None:
                logger.warning("status-publisher daemon died (code %s); restarting",
                               _status_daemon_proc.returncode)
                _start_status_publisher_daemon()
            tracked = fileserver.build_tracked_list()
            app_status.sync_app_status_rows(tracked)
        except Exception as e:  # noqa: BLE001 - never kill the loop
            logger.debug("fast status sync failed: %s", e)


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


def _reconcile_storage(cfg):
    """Re-derive upload state from PVC + Artifact CRs; self-heal after restarts."""
    try:
        cr = k8s.read_cr(CRD_GROUP, CRD_VERSION, CRD_PLURAL, CRD_NAME)
        if cr:
            uploads.reconcile_install_identity((cr.get("metadata") or {}).get("uid"))
        report = import_common.reconcile_local_uploads(cfg)
        snapshot = {
            **report,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with _storage_reconcile_lock:
            fileserver.set_storage_reconcile(snapshot)
        fileserver.invalidate_tracked_cache()
        sync_kick.set()
        if (report["repushed"] or report["staleWorkDirsRemoved"]
                or report["incompleteDirs"] or report["workDirsActive"]):
            logger.info(
                "Storage reconcile: %d stale work dir(s) removed, %d active work dir(s), "
                "%d incomplete dir(s), %d repush(es)",
                report["staleWorkDirsRemoved"], report["workDirsActive"],
                len(report["incompleteDirs"]), len(report["repushed"]),
            )
        for fail in report.get("repushFailed", []):
            logger.warning("Storage reconcile repush failed for %s: %s",
                           fail.get("uploadId"), fail.get("error"))
        return report
    except Exception as e:  # noqa: BLE001
        logger.warning("Storage reconcile failed: %s", e)
        return None


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
    fileserver.APP_VERSION[0] = VERSION
    app_status.APP_VERSION[0] = VERSION
    fileserver.IMPORT_KICK[0] = lambda: _run_imports_async(_read_config())
    fileserver.start_file_server(PORT)
    fileserver.write_healthz("starting", None)
    _start_status_publisher_daemon()

    _ensure_default_cr()

    # Dashboard sync starts immediately — it is cheap, self-healing (retries
    # the publisher daemon until eda-sa is reachable) and no-ops when rows are
    # unchanged, so the app appears on the dashboard within seconds of pod
    # start instead of after the reconcile settle delay.
    fileserver.SYNC_KICK[0] = sync_kick.set
    threading.Thread(target=_status_sync_loop, daemon=True, name="status-sync").start()
    threading.Thread(target=_artifact_watch_loop, daemon=True, name="artifact-watch").start()

    if STARTUP_DELAY_SECONDS > 0:
        logger.info("Deferring first reconcile for %ds so EDA install can settle",
                    STARTUP_DELAY_SECONDS)
        if shutdown_event.wait(timeout=STARTUP_DELAY_SECONDS):
            logger.info("Controller shutting down during startup delay")
            fileserver.stop_file_server()
            _stop_status_publisher_daemon()
            return

    cfg = _read_config()
    _reconcile_storage(cfg)

    while not shutdown_event.is_set():
        cycle_start = time.time()
        cfg = _read_config()
        fileserver.set_config(cfg)

        global _reconcile_cycle
        _reconcile_cycle += 1
        if _reconcile_cycle == 1 or _reconcile_cycle % 10 == 0:
            _reconcile_storage(cfg)

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
        reconcile_snap = fileserver.get_storage_reconcile()
        fileserver.write_healthz(
            health, now_str,
            extra={
                "storageReconcile": reconcile_snap.get("at"),
                "workDirsActive": reconcile_snap.get("workDirsActive", 0),
                "incompleteUploads": len(reconcile_snap.get("incompleteDirs") or []),
            },
        )
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
    _maybe_delete_pvc_on_uninstall()
    _stop_status_publisher_daemon()


if __name__ == "__main__":
    main()
