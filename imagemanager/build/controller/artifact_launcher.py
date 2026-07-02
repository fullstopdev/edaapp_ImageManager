"""
Sync cluster-scoped ImageManagerArtifact CRs for the EDA launcher dashlet.

EQL cannot query nested arrays (ImageManagerConfig.status.artifacts), so each
tracked upload is mirrored as its own cluster-scoped CR whose status carries the
launcher columns (displayName, sizeBytes, downloadStatus, open).
"""

import logging
import re

import k8s

logger = logging.getLogger("artifact_launcher")

IM_GROUP = "imagemanager.eda.edacommunity.com"
IM_VERSION = "v1alpha1"
IM_ARTIFACT_PLURAL = "imagemanagerartifacts"
MANAGED_LABEL = "imagemanager.eda.edacommunity.com/launcher"
MANAGED_VALUE = "true"
_NAME_RE = re.compile(r"[^a-z0-9.-]+")


def _cr_name(namespace, upload_id):
    """Stable cluster-scoped name: <namespace>--<uploadId> (DNS-safe)."""
    ns = _NAME_RE.sub("-", (namespace or "default").lower()).strip("-") or "default"
    uid = _NAME_RE.sub("-", (upload_id or "unknown").lower()).strip("-") or "unknown"
    name = f"{ns}--{uid}"
    return name[:253]


def _row_key(row):
    ns = row.get("namespace") or ""
    uid = row.get("uploadId") or row.get("name") or ""
    return (ns, uid)


def _desired_status(row):
    display = row.get("displayName") or row.get("name") or ""
    return {
        "displayName": display,
        "namespace": row.get("namespace", ""),
        "sizeBytes": row.get("sizeBytes"),
        "downloadStatus": row.get("downloadStatus", ""),
        "statusReason": row.get("statusReason", ""),
        "repo": row.get("repo", ""),
        "filePath": row.get("filePath", ""),
        "artifactName": row.get("name", ""),
        "open": "View",
    }


def _list_launcher_crs():
    try:
        return k8s.list_cluster_cr(IM_GROUP, IM_VERSION, IM_ARTIFACT_PLURAL) or []
    except Exception as e:
        logger.warning("list imagemanagerartifacts failed: %s", e)
        return []


def sync_launcher_rows(tracked_rows, startup_monotonic=None, grace_seconds=0):
    """Upsert/delete ImageManagerArtifact CRs to match tracked_rows."""
    _ = startup_monotonic, grace_seconds  # retained for API compat; grace removed in v0.0.10
    desired = {}
    for row in tracked_rows:
        ns, uid = _row_key(row)
        if not uid:
            continue
        desired[_cr_name(ns, uid)] = row

    existing = {}
    for cr in _list_launcher_crs():
        md = cr.get("metadata", {})
        labels = md.get("labels") or {}
        if labels.get(MANAGED_LABEL) != MANAGED_VALUE:
            continue
        existing[md.get("name", "")] = cr

    for name, row in desired.items():
        body = {
            "apiVersion": f"{IM_GROUP}/{IM_VERSION}",
            "kind": "ImageManagerArtifact",
            "metadata": {
                "name": name,
                "labels": {MANAGED_LABEL: MANAGED_VALUE},
            },
            "status": _desired_status(row),
        }
        if name in existing:
            cur = existing[name]
            if cur.get("status") == body["status"]:
                continue
            cur["status"] = body["status"]
            try:
                k8s.update_cr_status(IM_GROUP, IM_VERSION, IM_ARTIFACT_PLURAL, name, cur)
            except Exception as e:
                logger.warning("update imagemanagerartifact %s failed: %s", name, e)
        else:
            try:
                k8s.create_cr(IM_GROUP, IM_VERSION, IM_ARTIFACT_PLURAL, body)
            except Exception as e:
                logger.warning("create imagemanagerartifact %s failed: %s", name, e)

    for name in set(existing) - set(desired):
        try:
            k8s.delete_cr(IM_GROUP, IM_VERSION, IM_ARTIFACT_PLURAL, name)
        except Exception as e:
            logger.warning("delete imagemanagerartifact %s failed: %s", name, e)
