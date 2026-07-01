"""Reconciler for the ImageImport CRD.

Creating an ImageImport is the declarative equivalent of the web UI's
"Upload Image From File" dialog: point it at a URL instead of picking a
local file, and this loop does the rest -- download, detect, extract,
create Artifact(s) -- via the exact same import_common.process_zip()
pipeline the browser upload uses. Status is written back onto the CR itself
(phase/message/detectedNos/sizeBytes/artifacts/nodeProfileSnippet) so EDA's
generic resource table shows live progress with no need to open the app.

Polling, not watching (consistent with this controller's existing style in
main.py, which polls ImageManagerConfig/Artifacts every RECONCILE_INTERVAL
rather than running a watch loop).
"""

import logging
import os
import shutil
import ssl
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import artifact
import import_common
import k8s
import uploads

logger = logging.getLogger("imports")

GROUP = "imagemanager.eda.edacommunity.com"
VERSION = "v1alpha1"
PLURAL = "imageimports"
KIND = "ImageImport"

UPLOAD_DIR = "/data/uploads"
_DOWNLOAD_TIMEOUT = 300  # seconds; vendor NOS zips can be large

# Terminal phases: once reached, an ImageImport is left alone until its
# spec.sourceUrl (or generation) actually changes -- re-running a completed
# import would just hit process_zip()'s own "already exists" 409 guard, but
# skipping it here avoids needless downloads every reconcile cycle.
_TERMINAL_PHASES = {"Available", "Ready", "Failed", "Error"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _patch_status(namespace, name, obj, **fields):
    """Merge `fields` into obj['status'] and PUT it back."""
    status = dict(obj.get("status") or {})
    status.update(fields)
    obj["status"] = status
    try:
        k8s.update_namespaced_cr_status(GROUP, VERSION, namespace, PLURAL, name, obj)
    except Exception as e:  # noqa: BLE001 - never let a status-write failure crash reconcile
        logger.warning("status update failed for %s/%s: %s", namespace, name, e)


def _download(url, dest_path, insecure_skip_tls_verify):
    """Stream url into dest_path. Raises on any failure (caller sets Failed)."""
    ctx = None
    if url.lower().startswith("https://") and insecure_skip_tls_verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "eda-imagemanager-imports/1"})
    with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT, context=ctx) as resp, \
            open(dest_path, "wb") as out:
        shutil.copyfileobj(resp, out, length=1024 * 1024)


def _node_profile_snippet(result):
    """Best-effort one-liner mirroring what the web UI's "node profile" popup
    shows, good enough to paste into spec.images while looking at the CR."""
    nos = result.get("nos")
    if nos == "srl":
        return (f"- image: eda/{result['repo']}/{result['artifactName']}/{result['filePath']}\n"
                f"  imageMd5: eda/{result['repo']}/{result['artifactName']}-md5/"
                f"{result['filePath']}.md5")
    if nos == "sros":
        return f"# {result['fileCount']} boot-image Artifacts created under {result['repo']}/" \
               f"{result['artifactName']}-*; see the app UI for the full spec.images block."
    if nos == "srsim":
        return f"containerImage: eda-imagemanager.{import_common.POD_NAMESPACE}.svc/" \
               f"{result['artifactName']}:{result.get('imageTag', '')}"
    return ""


def _process_one(cr, config):
    namespace = cr["metadata"]["namespace"]
    name = cr["metadata"]["name"]
    spec = cr.get("spec") or {}
    source_url = (spec.get("sourceUrl") or "").strip()
    if not source_url:
        _patch_status(namespace, name, cr, phase="Error",
                      message="spec.sourceUrl is required", completionTime=_now())
        return

    _patch_status(namespace, name, cr, phase="Downloading",
                  message=f"Fetching {source_url}", startTime=_now())

    tmp_dir = tempfile.mkdtemp(dir=UPLOAD_DIR, prefix=".import-")
    try:
        tmp_zip = os.path.join(tmp_dir, "import.zip")
        try:
            _download(source_url, tmp_zip, bool(spec.get("insecureSkipTLSVerify")))
        except Exception as e:  # noqa: BLE001
            cr2 = k8s.read_namespaced_cr(GROUP, VERSION, namespace, PLURAL, name) or cr
            _patch_status(namespace, name, cr2, phase="Failed",
                          message=f"download failed: {e}", completionTime=_now())
            return

        cr2 = k8s.read_namespaced_cr(GROUP, VERSION, namespace, PLURAL, name) or cr
        _patch_status(namespace, name, cr2, phase="Extracting",
                      message="Detecting image type and creating Artifact(s)")

        filename = os.path.basename(source_url.split("?")[0]) or "import.zip"
        result = import_common.process_zip(
            tmp_dir, tmp_zip, filename, namespace,
            (spec.get("name") or "").strip(),
            {**config, **({"defaultRepo": spec["repo"]} if spec.get("repo") else {})},
        )

        cr3 = k8s.read_namespaced_cr(GROUP, VERSION, namespace, PLURAL, name) or cr2
        if not result.get("ok"):
            _patch_status(namespace, name, cr3, phase="Failed",
                          message=result.get("error", "import failed"), completionTime=_now())
            return

        # Optional license, mirroring the web UI's separate "attach license" step.
        upload_id = result["uploadId"]
        license_raw = None
        if spec.get("licenseKey"):
            license_raw = spec["licenseKey"].encode("utf-8")
        elif spec.get("licenseKeySecretRef"):
            sec = k8s.read_secret(spec["licenseKeySecretRef"], namespace)
            if sec:
                import base64
                data = (sec.get("data") or {}).get("license.key", "")
                license_raw = base64.b64decode(data) if data else None
        if license_raw:
            lic_result = import_common.attach_license(upload_id, license_raw)
            if not lic_result.get("ok"):
                logger.warning("license attach failed for %s/%s: %s",
                               namespace, name, lic_result.get("error"))

        phase = "Ready" if result.get("nos") == "srsim" else "Available"
        _patch_status(
            namespace, name, cr3,
            phase=phase,
            message="Import complete",
            detectedNos=result.get("nos", ""),
            sizeBytes=int(result.get("sizeBytes") or 0),
            nodeProfileSnippet=_node_profile_snippet(result),
            completionTime=_now(),
        )
        logger.info("ImageImport %s/%s complete (nos=%s, phase=%s)",
                    namespace, name, result.get("nos"), phase)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def reconcile(config):
    """Called once per RECONCILE_INTERVAL from main.py's loop. Processes every
    ImageImport that isn't already in a terminal phase. Synchronous/serial by
    design -- imports are infrequent and large; a slow one simply delays the
    next reconcile tick rather than needing a worker pool."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    try:
        items = k8s.list_cr_all_namespaces(GROUP, VERSION, PLURAL)
    except Exception as e:  # noqa: BLE001
        logger.warning("failed to list ImageImports: %s", e)
        return
    pending = [cr for cr in items
               if (cr.get("status") or {}).get("phase") not in _TERMINAL_PHASES]
    if not pending:
        return
    logger.info("Processing %d pending ImageImport(s)", len(pending))
    for cr in pending:
        ns = cr["metadata"]["namespace"]
        nm = cr["metadata"]["name"]
        try:
            _process_one(cr, config)
        except Exception as e:  # noqa: BLE001 - one bad CR must not wedge the loop
            logger.exception("ImageImport %s/%s reconcile crashed: %s", ns, nm, e)
            try:
                fresh = k8s.read_namespaced_cr(GROUP, VERSION, ns, PLURAL, nm)
                if fresh:
                    _patch_status(ns, nm, fresh, phase="Error",
                                  message=f"internal error: {e}", completionTime=_now())
            except Exception:  # noqa: BLE001
                pass
