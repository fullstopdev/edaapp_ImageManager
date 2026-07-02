"""Shared image-import logic, used by both:

  * fileserver.Handler._handle_upload  (POST /api/upload, from the browser)
  * imports.py                         (ImageImport CR reconcile loop)

This module is a refactor-out of what used to be inline in
fileserver.Handler._finish_srl_upload / _finish_sros_upload /
_finish_srsim_upload / _handle_license: the exact same detection, extraction,
Artifact-creation and license logic, just returning a plain result dict
instead of calling self._send_json. fileserver.py's Handler methods become
thin wrappers around process_zip()/attach_license() so behavior between a
manual upload and a declarative ImageImport is identical by construction.
"""

import logging
import os
import re
import shutil
import time
import urllib.error

import artifact
import k8s
import schemaprofile
import uploads

logger = logging.getLogger("import_common")

POD_NAMESPACE = os.environ.get("POD_NAMESPACE", "eda-system")
LICENSE_NS = POD_NAMESPACE
UPLOAD_DIR = "/data/uploads"
REPLACE_ANNOTATION = "imagemanager.eda.edacommunity.com/replace"

_VER_RE = re.compile(r"(\d+\.\d+\.[A-Za-z]?\d+(?:-\d+)?)")


def _err(status, message, **extra):
    out = {"ok": False, "status": status, "error": message}
    out.update(extra)
    return out


def _conflict_err(display_name, artifact_name, namespace, kind="image"):
    """409 with structured fields for the UI replace dialog."""
    if kind == "artifact":
        msg = (f"An Artifact named '{artifact_name}' already exists "
               f"in {namespace}. Delete it first.")
    else:
        msg = (f"An image named '{display_name}' already exists. "
               f"Delete it first to replace it.")
    return _err(409, msg, conflict=True, artifactName=artifact_name,
                displayName=display_name, namespace=namespace)


def image_exists_locally(upload_id):
    if not upload_id:
        return False
    return os.path.isfile(os.path.join(UPLOAD_DIR, upload_id, "meta.json"))


def artifact_cr_exists(namespace, name):
    if not namespace or not name:
        return False
    return k8s.read_namespaced_cr(
        artifact.ARTIFACT_GROUP, artifact.ARTIFACT_VERSION,
        namespace, artifact.ARTIFACT_PLURAL, name) is not None


def collect_artifact_names(meta, primary_name):
    """Artifact CR names tied to one upload (mirrors fileserver delete)."""
    if meta and meta.get("artifacts"):
        names = []
        for a in meta["artifacts"]:
            if a.get("artifactName"):
                names.append(a["artifactName"])
            if a.get("md5ArtifactName"):
                names.append(a["md5ArtifactName"])
        yang = meta.get("yang") or {}
        if yang.get("artifactName"):
            names.append(yang["artifactName"])
        return names
    md5_name = (meta or {}).get("md5ArtifactName") or ""
    yang = (meta or {}).get("yang") or {}
    return [n for n in (primary_name, md5_name, yang.get("artifactName")) if n]


def check_conflict(upload_id, namespace, display_name=None):
    """Return a 409 result dict when an upload id is already taken, else None."""
    if not upload_id:
        return None
    display_name = (display_name or upload_id).strip().lower()
    if image_exists_locally(upload_id):
        return _conflict_err(display_name, upload_id, namespace, "image")
    if artifact_cr_exists(namespace, upload_id):
        return _conflict_err(display_name, upload_id, namespace, "artifact")
    return None


def _artifact_names_for_upload(upload_id, namespace=None, primary_name=None):
    """Artifact CR names tied to one upload (for delete/repush)."""
    meta = uploads.read_meta(upload_id)
    namespace = namespace or (meta or {}).get("namespace")
    primary_name = primary_name or upload_id
    names = collect_artifact_names(meta, primary_name)
    if not meta:
        names = list(dict.fromkeys(names + [
            primary_name,
            primary_name + "-md5",
            primary_name + "-yang",
        ]))
    return namespace, names


def delete_artifacts_only(upload_id, namespace=None, primary_name=None):
    """Delete managed Artifact CRs for an upload; keep PVC files and license."""
    if not upload_id or any(c in upload_id for c in ("/", "\\", "..")):
        return _err(400, "valid upload id required")
    namespace, names = _artifact_names_for_upload(upload_id, namespace, primary_name)
    if namespace:
        for art_name in names:
            try:
                artifact.delete_artifact(namespace, art_name)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    return _err(502, f"Artifact delete failed (HTTP {e.code})")
    logger.info("Deleted %d artifact(s) for %s/%s (PVC retained)", len(names), namespace, upload_id)
    return None


def cleanup_existing(upload_id, namespace=None, primary_name=None):
    """Delete Artifact CRs, license ConfigMap, and PVC storage for an upload."""
    if not upload_id or any(c in upload_id for c in ("/", "\\", "..")):
        return _err(400, "valid upload id required")
    meta = uploads.read_meta(upload_id)
    namespace = namespace or (meta or {}).get("namespace")
    primary_name = primary_name or upload_id
    err = delete_artifacts_only(upload_id, namespace, primary_name)
    if err:
        return err
    lic = (meta or {}).get("license") or {}
    lic_cm = lic.get("configMap")
    if lic_cm:
        lic_ns = lic.get("namespace") or LICENSE_NS
        try:
            ex = k8s.read_configmap(lic_cm, lic_ns)
            owned = ((ex or {}).get("metadata", {}).get("labels", {}) or {}).get(
                artifact.MANAGED_LABEL) == "true"
            if ex is not None and owned:
                k8s.delete_configmap(lic_cm, lic_ns)
            elif ex is not None:
                logger.warning("refusing to delete non-managed ConfigMap %s/%s referenced "
                               "by %s", lic_ns, lic_cm, upload_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("license ConfigMap %s delete failed: %s", lic_cm, e)
    uploads.delete_upload(upload_id)
    logger.info("Removed upload %s/%s from PVC", namespace, upload_id)
    return None


def _create_artifact_with_retry(namespace, name, repo, file_path, file_url, md5_url=None):
    """Create an Artifact CR, retrying briefly if a prior delete is still Terminating."""
    for attempt in range(4):
        try:
            artifact.create_artifact(namespace, name, repo, file_path, file_url, md5_url)
            return None
        except urllib.error.HTTPError as e:
            if e.code == 409 and attempt < 3:
                time.sleep(1.0)
                continue
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            return _err(502, f"Artifact {name} create failed (HTTP {e.code}): {detail}")
        except Exception as e:  # noqa: BLE001
            return _err(502, f"Artifact {name} create failed: {e}")
    return _err(502, f"Artifact {name} create failed after retries")


def _repush_srl(meta, upload_id, namespace, base_url):
    repo = meta.get("repo") or "images"
    bin_filename = meta.get("filename") or ""
    if not bin_filename:
        return _err(400, "local image metadata is incomplete (missing filename)")
    file_path = meta.get("filePath") or bin_filename
    artifact_name = meta.get("artifactName") or upload_id
    display_name = meta.get("displayName") or artifact_name
    md5 = meta.get("md5") or ""
    md5_artifact_name = meta.get("md5ArtifactName") or (artifact_name + "-md5" if md5 else "")
    file_url, md5_url = artifact.file_urls(base_url, upload_id, bin_filename)
    err = _create_artifact_with_retry(namespace, artifact_name, repo, file_path,
                                    file_url, md5_url if md5 else None)
    if err:
        return err
    if md5 and md5_artifact_name:
        md5_file_path = file_path + ".md5"
        err = _create_artifact_with_retry(namespace, md5_artifact_name, repo,
                                          md5_file_path, md5_url, None)
        if err:
            return err
    yang = meta.get("yang") or {}
    if yang.get("artifactName") and yang.get("filename"):
        yurl, _ = artifact.file_urls(base_url, upload_id, yang["filename"])
        err = _create_artifact_with_retry(namespace, yang["artifactName"],
                                          artifact.SCHEMAPROFILE_REPO,
                                          yang.get("filePath") or yang["filename"],
                                          yurl, None)
        if err:
            return err
    return {"ok": True, "status": 200, "uploadId": upload_id, "artifactName": artifact_name,
            "displayName": display_name, "namespace": namespace, "repo": repo,
            "nos": "srl", "filePath": file_path, "md5": md5,
            "sizeBytes": meta.get("sizeBytes"), "repushed": True}


def _repush_sros(meta, upload_id, namespace, base_url):
    repo = meta.get("repo") or artifact.SROS_REPO
    display_name = meta.get("displayName") or upload_id
    art_records = meta.get("artifacts") or []
    if not art_records:
        return _err(400, "local SR OS image metadata is incomplete")
    for rec in art_records:
        fn = rec.get("filename") or rec.get("filePath")
        art_name = rec.get("artifactName")
        if not fn or not art_name:
            continue
        file_url, md5_url = artifact.file_urls(base_url, upload_id, fn)
        err = _create_artifact_with_retry(namespace, art_name, repo, fn, file_url,
                                        md5_url if rec.get("md5ArtifactName") else None)
        if err:
            return err
        md5_art = rec.get("md5ArtifactName")
        if md5_art:
            err = _create_artifact_with_retry(namespace, md5_art, repo, fn + ".md5",
                                              md5_url, None)
            if err:
                return err
    yang = meta.get("yang") or {}
    if yang.get("artifactName") and yang.get("filename"):
        yurl, _ = artifact.file_urls(base_url, upload_id, yang["filename"])
        err = _create_artifact_with_retry(namespace, yang["artifactName"],
                                          artifact.SCHEMAPROFILE_REPO,
                                          yang.get("filePath") or yang["filename"],
                                          yurl, None)
        if err:
            return err
    return {"ok": True, "status": 200, "uploadId": upload_id, "artifactName": upload_id,
            "displayName": display_name, "namespace": namespace,
            "repo": repo, "nos": "sros", "version": meta.get("version", ""),
            "fileCount": len(art_records), "sizeBytes": meta.get("sizeBytes"),
            "repushed": True}


def _repush_srsim(meta, upload_id, namespace, base_url):
    display_name = meta.get("displayName") or upload_id
    artifact_name = meta.get("artifactName") or upload_id
    yang = meta.get("yang") or {}
    if yang.get("artifactName") and yang.get("filename"):
        yurl, _ = artifact.file_urls(base_url, upload_id, yang["filename"])
        err = _create_artifact_with_retry(namespace, yang["artifactName"],
                                          artifact.SCHEMAPROFILE_REPO,
                                          yang.get("filePath") or yang["filename"],
                                          yurl, None)
        if err:
            return err
    return {"ok": True, "status": 200, "uploadId": upload_id, "artifactName": artifact_name,
            "displayName": display_name, "namespace": namespace, "nos": "srsim",
            "version": meta.get("version", ""), "imageTag": meta.get("imageTag"),
            "sizeBytes": meta.get("sizeBytes"), "repushed": True}


def repush_from_local(upload_id, config):
    """Recreate Artifact CRs from PVC files without re-downloading or re-extracting."""
    if not image_exists_locally(upload_id):
        return _err(404, f"no local image named '{upload_id}'")
    meta = uploads.read_meta(upload_id)
    if not meta:
        return _err(404, f"no metadata for '{upload_id}'")
    namespace = meta.get("namespace")
    if not namespace:
        return _err(400, "missing namespace in local image metadata")
    err = delete_artifacts_only(upload_id, namespace, meta.get("artifactName") or upload_id)
    if err:
        return err
    base_url = config.get("filePullBaseUrl") or artifact.default_base_url(POD_NAMESPACE)
    nos = meta.get("nos") or "srl"
    if nos == "srsim":
        return _repush_srsim(meta, upload_id, namespace, base_url)
    if meta.get("artifacts"):
        return _repush_sros(meta, upload_id, namespace, base_url)
    return _repush_srl(meta, upload_id, namespace, base_url)


def upload_needs_repush(meta, upload_id):
    """True when PVC meta exists but one or more expected Artifact CRs are missing."""
    if not meta:
        return False
    namespace = meta.get("namespace")
    if not namespace:
        return False
    primary = meta.get("artifactName") or upload_id
    for name in collect_artifact_names(meta, primary):
        if not artifact_cr_exists(namespace, name):
            return True
    return False


def reconcile_local_uploads(config):
    """Re-derive PVC vs Artifact state on startup (node-agent parity).

    Cleans stale in-flight temp dirs, reports incomplete uploads (meta missing),
    and repushes any upload whose bytes are on the PVC but Artifact CRs were
    lost (pod crash after finalize, manual CR delete, etc.).
    """
    report = {
        "staleWorkDirsRemoved": 0,
        "workDirsActive": 0,
        "incompleteDirs": [],
        "repushed": [],
        "repushFailed": [],
        "incompleteBytes": 0,
    }
    try:
        artifact.purge_orphan_managed_artifacts(uploads.list_meta)
    except Exception as e:  # noqa: BLE001
        logger.warning("Orphan Artifact purge failed: %s", e)
    report["staleWorkDirsRemoved"] = uploads.cleanup_stale_work_dirs()
    report["workDirsActive"] = uploads.count_work_dirs()
    incomplete = uploads.scan_incomplete_dirs()
    report["incompleteDirs"] = incomplete
    report["incompleteBytes"] = sum(d.get("bytes") or 0 for d in incomplete)
    for meta in uploads.list_meta():
        uid = meta.get("uploadId") or meta.get("artifactName") or ""
        if not uid or not upload_needs_repush(meta, uid):
            continue
        logger.info("Storage reconcile: repushing %s (PVC present, Artifact CR missing)", uid)
        result = repush_from_local(uid, config)
        if result.get("ok"):
            report["repushed"].append(uid)
        else:
            report["repushFailed"].append({
                "uploadId": uid,
                "error": result.get("error") or "repush failed",
            })
    return report


def _ensure_replace(upload_id, display_name, artifact_name, namespace, replace):
    """When replace is set, drop Artifact CRs only (PVC kept for repush); else 409."""
    if replace:
        return delete_artifacts_only(upload_id, namespace, artifact_name)
    if image_exists_locally(upload_id):
        return _conflict_err(display_name, artifact_name, namespace, "image")
    if artifact_cr_exists(namespace, artifact_name):
        return _conflict_err(display_name, artifact_name, namespace, "artifact")
    return None


def _create_yang_artifact(namespace, upload_id, yname, yang_filename, base_url):
    """Best-effort YANG Artifact creation; never raises. Same retry-on-409
    behavior as the original (a re-uploaded image's old Artifact may still be
    Terminating)."""
    file_url, _ = artifact.file_urls(base_url, upload_id, yang_filename)
    for attempt in range(4):
        try:
            artifact.create_artifact(namespace, yname, artifact.SCHEMAPROFILE_REPO,
                                      yang_filename, file_url, None)
            return True, {"artifactName": yname, "filename": yang_filename,
                          "filePath": yang_filename, "repo": artifact.SCHEMAPROFILE_REPO}
        except urllib.error.HTTPError as e:
            if e.code == 409 and attempt < 3:
                time.sleep(1.0)
                continue
            logger.warning("YANG Artifact %s/%s create failed (HTTP %s)",
                           namespace, yname, e.code)
            return False, None
        except Exception as e:  # noqa: BLE001 - YANG is best-effort
            logger.warning("YANG Artifact %s/%s create error: %s", namespace, yname, e)
            return False, None


def _process_srl(tmp_zip, filename, namespace, name_override, config, replace=False):
    repo = (config.get("defaultRepo") or "images").strip()
    display_name = (name_override or uploads.derive_name(filename)).strip().lower()
    artifact_name = uploads.to_k8s_name(display_name)
    if not artifact_name:
        return _err(400, "could not derive a valid image name")
    upload_dir = os.path.join(UPLOAD_DIR, artifact_name)
    err = _ensure_replace(artifact_name, display_name, artifact_name, namespace, replace)
    if err:
        return err
    shutil.rmtree(upload_dir, ignore_errors=True)
    os.makedirs(upload_dir, exist_ok=True)
    try:
        bin_filename, md5 = uploads.extract_image_from_zip(tmp_zip, upload_dir)
    except uploads.BadZip as e:
        shutil.rmtree(upload_dir, ignore_errors=True)
        return _err(400, f"could not read the zip: {e}")
    written = os.path.getsize(os.path.join(upload_dir, bin_filename))
    md5_artifact_name = (artifact_name + "-md5") if md5 else ""
    image_file_path = bin_filename
    md5_file_path = bin_filename + ".md5"
    uploads.finalize_upload(artifact_name, bin_filename, md5, repo, image_file_path,
                            namespace, written, artifact_name, display_name, md5_artifact_name)
    base_url = config.get("filePullBaseUrl") or artifact.default_base_url(POD_NAMESPACE)
    file_url, md5_url = artifact.file_urls(base_url, artifact_name, bin_filename)
    try:
        artifact.create_artifact(namespace, artifact_name, repo, image_file_path,
                                  file_url, md5_url if md5 else None)
    except urllib.error.HTTPError as e:
        if e.code == 409 and replace:
            delete_artifacts_only(artifact_name, namespace, artifact_name)
            try:
                artifact.create_artifact(namespace, artifact_name, repo, image_file_path,
                                          file_url, md5_url if md5 else None)
            except urllib.error.HTTPError as e2:
                shutil.rmtree(upload_dir, ignore_errors=True)
                if e2.code == 409:
                    return _conflict_err(display_name, artifact_name, namespace, "artifact")
                detail = ""
                try:
                    detail = e2.read().decode("utf-8", errors="replace")[:300]
                except Exception:  # noqa: BLE001
                    pass
                return _err(502, f"Artifact create failed (HTTP {e2.code}): {detail}")
            except Exception as e2:  # noqa: BLE001
                shutil.rmtree(upload_dir, ignore_errors=True)
                return _err(502, f"Artifact create failed: {e2}")
        else:
            shutil.rmtree(upload_dir, ignore_errors=True)
            if e.code == 409:
                return _conflict_err(display_name, artifact_name, namespace, "artifact")
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            return _err(502, f"Artifact create failed (HTTP {e.code}): {detail}")
    except Exception as e:  # noqa: BLE001 - don't orphan the extracted file
        shutil.rmtree(upload_dir, ignore_errors=True)
        return _err(502, f"Artifact create failed: {e}")
    if md5:
        try:
            artifact.create_artifact(namespace, md5_artifact_name, repo,
                                      md5_file_path, md5_url, None)
        except Exception as e:  # noqa: BLE001 - md5 sidecar is best-effort
            logger.warning("md5 Artifact %s/%s create failed: %s", namespace, md5_artifact_name, e)
    yang_created = False
    try:
        vm = _VER_RE.search(display_name)
        srl_ver = vm.group(1).split("-")[0] if vm else ""
        if srl_ver:
            yfn, _src = schemaprofile.resolve_yang("srl", srl_ver, upload_dir)
            if yfn:
                ok, yrec = _create_yang_artifact(namespace, artifact_name,
                                                  artifact_name + "-yang", yfn, base_url)
                if ok:
                    m = uploads.read_meta(artifact_name) or {}
                    m["yang"] = yrec
                    m["nos"] = "srl"
                    m["version"] = srl_ver
                    uploads.rewrite_meta(artifact_name, m)
                    yang_created = True
    except Exception as e:  # noqa: BLE001 - YANG is best-effort
        logger.warning("SRL YANG handling failed for %s: %s", artifact_name, e)
    return {"ok": True, "status": 200, "uploadId": artifact_name, "artifactName": artifact_name,
            "displayName": display_name, "namespace": namespace, "repo": repo,
            "nos": "srl", "filePath": image_file_path, "md5": md5 or "",
            "sizeBytes": written, "yangCreated": yang_created}


def _process_sros(tmp_dir, tmp_zip, namespace, name_override, config, replace=False):
    try:
        version_disp, extracted = uploads.extract_sros_images(tmp_zip, tmp_dir)
    except uploads.BadZip as e:
        return _err(400, f"not a 7750 SR OS image: {e}")
    version = version_disp.lower()
    display_name = (name_override or ("sros-" + version)).strip().lower()
    group_id = uploads.to_k8s_name(display_name)
    if not group_id:
        return _err(400, "could not derive a valid image name")
    group_dir = os.path.join(UPLOAD_DIR, group_id)
    err = _ensure_replace(group_id, display_name, group_id, namespace, replace)
    if err:
        return err
    shutil.rmtree(group_dir, ignore_errors=True)
    os.makedirs(group_dir, exist_ok=True)
    total = 0
    for it in extracted:
        os.replace(os.path.join(tmp_dir, it["filename"]),
                   os.path.join(group_dir, it["filename"]))
        total += int(it.get("size") or 0)

    base_url = config.get("filePullBaseUrl") or artifact.default_base_url(POD_NAMESPACE)
    created = []
    art_records = []

    def rollback():
        for ns_, nm_ in created:
            try:
                artifact.delete_artifact(ns_, nm_)
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(group_dir, ignore_errors=True)

    for it in extracted:
        fn = it["filename"]
        md5 = it.get("md5")
        art_name = uploads.to_k8s_name(group_id + "-" + fn)
        file_url, md5_url = artifact.file_urls(base_url, group_id, fn)
        if md5:
            with open(os.path.join(group_dir, fn + ".md5"), "w") as f:
                f.write(md5 + "\n")
        try:
            artifact.create_artifact(namespace, art_name, artifact.SROS_REPO,
                                      fn, file_url, md5_url if md5 else None)
        except urllib.error.HTTPError as e:
            rollback()
            if e.code == 409:
                return _conflict_err(display_name, group_id, namespace, "artifact")
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:  # noqa: BLE001
                pass
            return _err(502, f"Artifact {art_name} create failed (HTTP {e.code}): {detail}")
        except Exception as e:  # noqa: BLE001 - roll back, never orphan
            rollback()
            return _err(502, f"Artifact {art_name} create failed: {e}")
        created.append((namespace, art_name))
        rec = {"artifactName": art_name, "filename": fn, "filePath": fn}
        if md5:
            md5_art = uploads.to_k8s_name(art_name + "-md5")
            try:
                artifact.create_artifact(namespace, md5_art, artifact.SROS_REPO,
                                          fn + ".md5", md5_url, None)
                created.append((namespace, md5_art))
                rec["md5ArtifactName"] = md5_art
            except Exception as e:  # noqa: BLE001 - md5 sidecar is best-effort
                logger.warning("md5 Artifact %s/%s create failed: %s", namespace, md5_art, e)
        art_records.append(rec)

    yang_meta = None
    try:
        yfn, src = schemaprofile.resolve_yang("sros", version, group_dir)
        if yfn:
            ok, yang_meta = _create_yang_artifact(namespace, group_id, group_id, yfn, base_url)
            if ok:
                total += os.path.getsize(os.path.join(group_dir, yfn))
                note = ("YANG schema profile auto-fetched from nokia-eda/schema-profiles."
                        if src == "published" else
                        "YANG schema profile built from nokia/7x50_YangModels.")
            else:
                note = "Image artifacts created, but the YANG schema-profile Artifact failed."
        else:
            note = (f"Image artifacts created. Could not obtain a YANG schema profile for "
                    f"{version} (not published upstream and no 7x50 tag).")
    except Exception as e:  # noqa: BLE001 - YANG is best-effort; keep the image artifacts
        logger.warning("YANG handling failed for %s: %s", group_id, e)
        yang_meta = None
        note = "Image artifacts created; the YANG step failed."

    uploads.finalize_group(group_id, display_name, "sros", namespace, artifact.SROS_REPO,
                           art_records, yang_meta, total, version)
    return {"ok": True, "status": 200, "uploadId": group_id, "artifactName": group_id,
            "displayName": display_name, "namespace": namespace,
            "repo": artifact.SROS_REPO, "nos": "sros", "version": version,
            "fileCount": len(extracted), "sizeBytes": total,
            "yangCreated": bool(yang_meta), "note": note}


def _process_srsim(tmp_zip, filename, namespace, name_override, config, replace=False):
    display_name = (name_override or uploads.derive_name(filename)).strip().lower()
    artifact_name = uploads.to_k8s_name(display_name)
    if not artifact_name:
        return _err(400, "could not derive a valid image name")
    image_dir = os.path.join(UPLOAD_DIR, artifact_name)
    err = _ensure_replace(artifact_name, display_name, artifact_name, namespace, replace)
    if err:
        return err
    shutil.rmtree(image_dir, ignore_errors=True)
    os.makedirs(image_dir, exist_ok=True)
    try:
        oci = uploads.extract_srsim_image(tmp_zip, image_dir)
    except uploads.BadZip as e:
        shutil.rmtree(image_dir, ignore_errors=True)
        return _err(400, f"could not read the SR-SIM image: {e}")
    except Exception as e:  # noqa: BLE001 - never leave a partial OCI layout
        shutil.rmtree(image_dir, ignore_errors=True)
        logger.warning("SR-SIM extract failed for %s: %s", artifact_name, e)
        return _err(500, f"failed to unpack the SR-SIM image: {e}")
    version = oci.get("version") or ""
    yang_meta = None
    base_url = config.get("filePullBaseUrl") or artifact.default_base_url(POD_NAMESPACE)
    try:
        if version:
            yfn, _src = schemaprofile.resolve_yang("sros", version, image_dir)
            if yfn:
                ok, yang_meta = _create_yang_artifact(namespace, artifact_name,
                                                       artifact_name + "-yang", yfn, base_url)
                if not ok:
                    yang_meta = None
    except Exception as e:  # noqa: BLE001 - YANG is best-effort
        logger.warning("SR-SIM YANG handling failed for %s: %s", artifact_name, e)
        yang_meta = None
    uploads.finalize_srsim(artifact_name, display_name, namespace, oci, yang_meta)
    logger.info("SR-SIM processed: %s (%d bytes, tag %s, yang=%s)",
                display_name, oci.get("sizeBytes") or 0, oci.get("tag"), bool(yang_meta))
    return {"ok": True, "status": 200, "uploadId": artifact_name, "artifactName": artifact_name,
            "displayName": display_name, "namespace": namespace, "nos": "srsim",
            "version": version, "imageTag": oci.get("tag"),
            "sizeBytes": oci.get("sizeBytes"), "yangCreated": bool(yang_meta)}


def process_zip(tmp_dir, tmp_zip, filename, namespace, name_override, config, replace=False):
    """Detect the NOS in tmp_zip and dispatch to the matching processor.
    Returns a result dict: {"ok": True, ...fields} or
    {"ok": False, "status": <http-like code>, "error": <message>}.
    Identical outcome to a manual browser upload of the same zip.
    """
    if not uploads.looks_like_zip(tmp_zip):
        return _err(400, "the file is not a valid .zip archive")
    nos = uploads.detect_nos_from_zip(tmp_zip)
    if nos == "srsim":
        return _process_srsim(tmp_zip, filename, namespace, name_override, config, replace)
    if nos == "sros":
        return _process_sros(tmp_dir, tmp_zip, namespace, name_override, config, replace)
    if nos == "srl":
        return _process_srl(tmp_zip, filename, namespace, name_override, config, replace)
    return _err(400, "could not detect an SR Linux (.bin), SR OS 7750 TiMOS, "
                     "or SR-SIM (srsim.tar.xz) image inside the zip")


def attach_license(upload_id, raw_bytes, license_filename=""):
    """Attach a license key to an already-processed image. Same ownership
    guard and ConfigMap semantics as the browser's /api/license endpoint.
    Returns a result dict in the same {"ok": ...} shape as process_zip().
    """
    src_filename = uploads.sanitize_filename(license_filename) if license_filename else ""
    meta = uploads.read_meta(upload_id)
    if not meta:
        return _err(404, f"no image named '{upload_id}'")
    if len(raw_bytes) > uploads._LICENSE_MAX:  # noqa: SLF001
        return _err(413, "license file too large (expected a small key file)")
    key = uploads.normalize_license(raw_bytes)
    if not key:
        return _err(400, "could not find a valid license key in the text "
                         "(expected a line like '<node-id> <key>')")
    image_nos = meta.get("nos") or "srl"
    expect = "srl" if image_nos == "srl" else "sros"
    lic_nos = uploads.detect_license_nos(key, src_filename)
    mismatch = bool(lic_nos and lic_nos != expect)
    cm_name = uploads.license_cm_name(upload_id)
    labels = {artifact.MANAGED_LABEL: "true"}
    data = {uploads.LICENSE_KEY: key}
    try:
        existing = k8s.read_configmap(cm_name, LICENSE_NS)
    except Exception as e:  # noqa: BLE001
        return _err(502, f"could not read existing ConfigMap: {e}")
    if existing is not None and \
            ((existing.get("metadata") or {}).get("labels") or {}).get(
                artifact.MANAGED_LABEL) != "true":
        return _err(409, f"a ConfigMap named '{cm_name}' already exists in {LICENSE_NS} "
                         f"and is not managed by Image Manager (it may be an EDA-owned "
                         f"license). Rename the image and retry.")
    fresh = existing is None
    try:
        if fresh:
            k8s.create_configmap(cm_name, LICENSE_NS, data, labels)
        else:
            k8s.replace_configmap(cm_name, LICENSE_NS, data, labels)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        return _err(502, f"license ConfigMap write failed (HTTP {e.code}): {detail}")
    except Exception as e:  # noqa: BLE001
        return _err(502, f"license ConfigMap write failed: {e}")
    uploads.store_license_file(upload_id, key)
    lic_rec = {"configMap": cm_name, "namespace": LICENSE_NS, "key": uploads.LICENSE_KEY,
               "nos": lic_nos or expect, "sourceFilename": src_filename or None,
               "sizeBytes": len(key)}
    recorded = None
    try:
        recorded = uploads.set_license_meta(upload_id, lic_rec)
    except OSError as e:
        logger.warning("license meta write failed for %s: %s", upload_id, e)
    if recorded is None:
        if fresh:
            try:
                k8s.delete_configmap(cm_name, LICENSE_NS)
            except Exception:  # noqa: BLE001
                pass
        return _err(409, "could not record the license on the image (it may have "
                         "been deleted, or storage is full)")
    logger.info("License attached to %s -> ConfigMap %s/%s (%d bytes, nos=%s, mismatch=%s)",
                upload_id, LICENSE_NS, cm_name, len(key), lic_nos, mismatch)
    return {"ok": True, "status": 200, "uploadId": upload_id, "configMap": cm_name,
            "namespace": LICENSE_NS, "licenseNos": lic_nos,
            "imageNos": image_nos, "mismatch": mismatch}
