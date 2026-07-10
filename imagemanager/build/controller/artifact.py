"""
Build and create EDA Artifact CRs (artifacts.eda.nokia.com/v1).

The Artifact's remoteFileUrl points back at THIS app's in-cluster HTTPS
file-serve endpoint. The built-in artifact server (eda-asvr) then pulls the
file from us, validates it against the md5, and re-hosts it. eda-asvr's pull
client does NOT trust eda-internal-ca by default, so each Artifact also sets
spec.trustBundle to a per-namespace ConfigMap holding our serving CA (see
ensure_trust_bundle); without it the pull fails x509 unknown-authority.
"""

import logging
import os
from urllib.parse import quote, urlsplit

import k8s

logger = logging.getLogger("artifact")

ARTIFACT_GROUP = "artifacts.eda.nokia.com"
ARTIFACT_VERSION = "v1"
ARTIFACT_PLURAL = "artifacts"

# EDA repo conventions consumed by NodeProfiles. SR Linux uploads use the
# config-driven defaultRepo ("images"); SR OS boot images and their YANG schema
# profile go to the repos the reference SR OS NodeProfiles expect.
SROS_REPO = "srosimages"
SCHEMAPROFILE_REPO = "schemaprofiles"

MANAGED_LABEL = "imagemanager.eda.edacommunity.com/managed"
SERVICE_NAME = "eda-imagemanager"
SERVICE_PORT = 8443

# eda-asvr's pull client does NOT trust eda-internal-ca by default, so each
# Artifact must point spec.trustBundle at a ConfigMap holding the CA that signs
# our serving cert. The CSI driver writes that CA here; we replicate it into a
# ConfigMap (key trust-bundle.pem, the EDA convention) in the artifact's
# namespace, since eda-internal-trust-bundle is only present in eda-system.
TRUST_BUNDLE_CM = "imagemanager-trust-bundle"
TRUST_BUNDLE_KEY = "trust-bundle.pem"
SERVING_CA_PATH = "/var/run/eda/tls/serving/ca.crt"


def _serving_ca():
    """Read the CA that signs our serving cert (CSI may rotate it in place)."""
    try:
        with open(SERVING_CA_PATH) as f:
            return f.read()
    except OSError:
        return ""


def _normalize_pem(pem):
    return (pem or "").strip()


def ensure_trust_bundle(namespace):
    """Ensure a trust-bundle ConfigMap with our serving CA exists in `namespace`.
    Creates or updates the ConfigMap when the CSI serving CA rotates.
    Returns the ConfigMap name, or None if we have no CA (plain-HTTP mode)."""
    ca = _serving_ca()
    if not ca.strip():
        return None
    data = {TRUST_BUNDLE_KEY: ca}
    cm = k8s.read_configmap(TRUST_BUNDLE_CM, namespace)
    if cm is None:
        try:
            k8s.create_configmap(TRUST_BUNDLE_CM, namespace, data)
            logger.info("Created trust bundle ConfigMap %s/%s", namespace, TRUST_BUNDLE_CM)
        except Exception as e:
            logger.warning("Failed to create trust bundle CM in %s: %s", namespace, e)
            return None
        return TRUST_BUNDLE_CM
    existing = _normalize_pem((cm.get("data") or {}).get(TRUST_BUNDLE_KEY))
    if existing == _normalize_pem(ca):
        return TRUST_BUNDLE_CM
    try:
        k8s.replace_configmap(TRUST_BUNDLE_CM, namespace, data)
        logger.info("Updated trust bundle ConfigMap %s/%s (serving CA changed)",
                    namespace, TRUST_BUNDLE_CM)
    except Exception as e:
        logger.warning("Failed to update trust bundle CM in %s: %s", namespace, e)
        return None
    return TRUST_BUNDLE_CM


def refresh_trust_bundles(namespaces):
    """Refresh per-namespace trust bundles (e.g. after internal-CA rotation)."""
    updated = []
    for ns in sorted({n for n in namespaces if n}):
        before = k8s.read_configmap(TRUST_BUNDLE_CM, ns)
        before_pem = _normalize_pem(((before or {}).get("data") or {}).get(TRUST_BUNDLE_KEY))
        name = ensure_trust_bundle(ns)
        if not name:
            continue
        after = k8s.read_configmap(TRUST_BUNDLE_CM, ns)
        after_pem = _normalize_pem(((after or {}).get("data") or {}).get(TRUST_BUNDLE_KEY))
        if before_pem != after_pem:
            updated.append(ns)
    if updated:
        logger.info("Refreshed trust bundle in namespace(s): %s", ", ".join(updated))
    return updated


def default_base_url(pod_namespace):
    """In-cluster HTTPS base eda-asvr uses to pull from us (cert SAN host)."""
    return f"https://{SERVICE_NAME}.{pod_namespace}.svc:{SERVICE_PORT}/"


def file_urls(base_url, upload_id, filename):
    """(fileUrl, md5Url) for an upload, rooted at base_url."""
    root = (base_url or "").rstrip("/")
    f = f"{root}/files/{quote(upload_id, safe='')}/{quote(filename, safe='')}"
    return f, f + ".md5"


def build_artifact(namespace, name, repo, file_path, file_url, md5_url=None, trust_bundle=None):
    remote = {"fileUrl": file_url}
    if md5_url:
        remote["md5Url"] = md5_url
    spec = {
        "repo": repo,
        "filePath": file_path,
        "remoteFileUrl": remote,
    }
    if trust_bundle:
        spec["trustBundle"] = trust_bundle
    return {
        "apiVersion": f"{ARTIFACT_GROUP}/{ARTIFACT_VERSION}",
        "kind": "Artifact",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {MANAGED_LABEL: "true"},
        },
        "spec": spec,
    }


def create_artifact(namespace, name, repo, file_path, file_url, md5_url=None):
    # eda-asvr pulls over HTTPS and must trust our internal-CA serving cert.
    trust_bundle = ensure_trust_bundle(namespace)
    body = build_artifact(namespace, name, repo, file_path, file_url, md5_url, trust_bundle)
    logger.info("Creating Artifact %s/%s (repo=%s filePath=%s md5=%s trustBundle=%s) fileUrl=%s",
                namespace, name, repo, file_path, bool(md5_url), trust_bundle, file_url)
    return k8s.create_namespaced_cr(
        ARTIFACT_GROUP, ARTIFACT_VERSION, namespace, ARTIFACT_PLURAL, body
    )


def delete_artifact(namespace, name):
    """Delete an Artifact CR (eda-asvr drops its re-hosted copy too). 404 -> None."""
    logger.info("Deleting Artifact %s/%s", namespace, name)
    return k8s.delete_namespaced_cr(
        ARTIFACT_GROUP, ARTIFACT_VERSION, namespace, ARTIFACT_PLURAL, name
    )


def list_managed_artifacts():
    """All Artifacts this app created, across namespaces (label-selected)."""
    return k8s.list_cr_all_namespaces(
        ARTIFACT_GROUP, ARTIFACT_VERSION, ARTIFACT_PLURAL,
        label_selector=f"{MANAGED_LABEL}=true",
    )


def upload_id_from_cr(art):
    """Best-effort upload id from spec.remoteFileUrl (/files/<uploadId>/...)."""
    spec = art.get("spec", {}) or {}
    remote = spec.get("remoteFileUrl") or {}
    url = remote.get("fileUrl") or remote.get("md5Url") or ""
    if "/files/" not in url:
        return ""
    try:
        after = url.split("/files/", 1)[1]
        return after.split("/", 1)[0]
    except (IndexError, ValueError):
        return ""


def delete_all_managed_artifacts():
    """Remove every Artifact CR labelled managed by Image Manager."""
    deleted = 0
    for art in list_managed_artifacts():
        md = art.get("metadata", {}) or {}
        ns = md.get("namespace", "")
        name = md.get("name", "")
        if not ns or not name:
            continue
        try:
            delete_artifact(ns, name)
            deleted += 1
        except Exception as e:  # noqa: BLE001 — best-effort bulk cleanup
            logger.warning("Failed to delete managed Artifact %s/%s: %s", ns, name, e)
    if deleted:
        logger.info("Deleted %d managed Artifact CR(s)", deleted)
    return deleted


def purge_orphan_managed_artifacts(list_meta_fn):
    """Drop managed Artifact CRs with no PVC meta (post-uninstall / reinstall ghosts).

    Keeps CRs that are still downloading; eda-asvr-only copies (Available/Ready)
    without local bytes are removed so the dashboard matches PVC state.
    """
    covered = set()
    for m in list_meta_fn():
        covered.add((m.get("namespace"), m.get("uploadId") or m.get("artifactName")))

    removed = 0
    for art in list_managed_artifacts():
        md = art.get("metadata", {}) or {}
        if md.get("deletionTimestamp"):
            continue
        ns = md.get("namespace", "")
        name = md.get("name", "")
        if not ns or not name or name.endswith("-md5"):
            continue
        upload_id = upload_id_from_cr(art) or name
        if (ns, upload_id) in covered:
            continue
        ds = ((art.get("status") or {}).get("downloadStatus") or "").lower()
        if ds in ("downloading", "pending", "inprogress", "in progress"):
            continue
        try:
            delete_artifact(ns, name)
            removed += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to purge orphan Artifact %s/%s: %s", ns, name, e)
    if removed:
        logger.info("Purged %d orphan managed Artifact CR(s) (no PVC meta)", removed)
    return removed


def artifact_status(namespace, name):
    """Live status dict for one Artifact, or {} if missing."""
    cr = k8s.read_namespaced_cr(
        ARTIFACT_GROUP, ARTIFACT_VERSION, namespace, ARTIFACT_PLURAL, name
    )
    return (cr or {}).get("status", {}) or {}


def asvr_path(internal_url):
    """Convert an Artifact status.internalUrl into the artifact-server path used
    in a NodeProfile's spec.images[].image (host stripped). e.g.
    https://eda-asvr.eda-system.svc/eda/images/srlinux-26.3.2/srlinux-26.3.2
    -> eda/images/srlinux-26.3.2/srlinux-26.3.2 . Returns "" if not available."""
    if not internal_url:
        return ""
    try:
        return urlsplit(internal_url).path.lstrip("/")
    except Exception:
        return ""


ASVR_SERVICE = "eda-asvr"


def asvr_public_base_url(artifact_namespace, pod_namespace=None):
    """HTTPS base URL eda-asvr exposes artifacts at for NodeProfile yang:/llmDb:.

    e.g. https://eda-asvr.eda-system.svc/eda-system/
    """
    ns = (artifact_namespace or "").strip().strip("/")
    pod_ns = (pod_namespace or os.environ.get("POD_NAMESPACE", "eda-system")).strip()
    if not ns:
        return ""
    return f"https://{ASVR_SERVICE}.{pod_ns}.svc/{ns}/"


def yang_public_url(artifact_namespace, profile_name, zip_filename, pod_namespace=None):
    """Full eda-asvr URL for NodeProfile spec.yang (schemaprofiles repo)."""
    base = asvr_public_base_url(artifact_namespace, pod_namespace)
    profile = (profile_name or "").strip().strip("/")
    zf = (zip_filename or "").strip().lstrip("/")
    if not base or not profile or not zf:
        return ""
    return f"{base}{SCHEMAPROFILE_REPO}/{profile}/{zf}"


def _version_dashed(version):
    return (version or "").strip().lower().replace(".", "-")


def llm_embedding_basename(nos, version):
    """Tarball file name under llm-dbs/llm-db-<profile>/ on eda-asvr."""
    n = (nos or "").strip().lower()
    token = "srlinux" if n == "srl" else "sros" if n == "sros" else n
    vd = _version_dashed(version)
    if not token or not vd:
        return ""
    return f"llm-embeddings-{token}-{vd}.tar.gz"


def llm_db_public_url(artifact_namespace, profile_name, nos, version, pod_namespace=None):
    """Full eda-asvr URL for NodeProfile spec.llmDb."""
    base = asvr_public_base_url(artifact_namespace, pod_namespace)
    profile = (profile_name or "").strip().strip("/")
    tarball = llm_embedding_basename(nos, version)
    if not base or not profile or not tarball:
        return ""
    return f"{base}llm-dbs/llm-db-{profile}/{tarball}"
