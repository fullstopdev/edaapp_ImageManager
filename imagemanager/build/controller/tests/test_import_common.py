"""Unit tests for import_common.py pure-logic helpers."""

from __future__ import annotations

import import_common


def test_collect_artifact_names_from_artifacts_list():
    meta = {
        "artifacts": [
            {"artifactName": "img-a", "md5ArtifactName": "img-a-md5"},
            {"artifactName": "img-b", "md5ArtifactName": "img-b-md5"},
        ],
        "yang": {"artifactName": "img-yang"},
    }
    names = import_common.collect_artifact_names(meta, "primary")
    assert names == ["img-a", "img-a-md5", "img-b", "img-b-md5", "img-yang"]


def test_collect_artifact_names_legacy_shape():
    meta = {
        "md5ArtifactName": "legacy-md5",
        "yang": {"artifactName": "legacy-yang"},
    }
    names = import_common.collect_artifact_names(meta, "legacy-img")
    assert names == ["legacy-img", "legacy-md5", "legacy-yang"]


def test_artifact_names_for_upload_without_meta(monkeypatch):
    import uploads

    monkeypatch.setattr(uploads, "read_meta", lambda _uid: None)
    ns, names = import_common._artifact_names_for_upload("my-upload", "eda", "my-upload")
    assert ns == "eda"
    assert names == ["my-upload", "my-upload-md5", "my-upload-yang"]
