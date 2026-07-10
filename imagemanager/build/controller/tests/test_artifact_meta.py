"""Tests for post-upload NodeProfile option updates."""

from __future__ import annotations

import json

import import_common
import uploads


def test_update_artifact_meta_sets_and_clears_fields(tmp_path, monkeypatch):
    upload_id = "my-image"
    d = tmp_path / upload_id
    d.mkdir()
    meta = {"uploadId": upload_id, "artifactName": upload_id, "nos": "sros", "namespace": "eda"}
    (d / "meta.json").write_text(json.dumps(meta))

    monkeypatch.setattr(uploads, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(uploads, "read_meta", uploads.read_meta)
    monkeypatch.setattr(uploads, "rewrite_meta", uploads.rewrite_meta)

    url = "https://eda-asvr.eda-system.svc/eda/llm-dbs/srl-26/srl-26.tar.gz"
    yang = "https://eda-asvr.eda-system.svc/eda/schemaprofiles/custom/custom.zip"
    r = import_common.update_artifact_meta(upload_id, llm_db=url, yang_override=yang)
    assert r["ok"] is True
    stored = uploads.read_meta(upload_id)
    assert stored["llmDb"] == url
    assert stored["yangOverride"] == yang

    r2 = import_common.update_artifact_meta(upload_id, llm_db="", yang_override="")
    assert r2["ok"] is True
    stored2 = uploads.read_meta(upload_id)
    assert "llmDb" not in stored2
    assert "yangOverride" not in stored2


def test_update_artifact_meta_rejects_bad_url(tmp_path, monkeypatch):
    upload_id = "img-bad"
    d = tmp_path / upload_id
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"uploadId": upload_id}))

    monkeypatch.setattr(uploads, "DATA_DIR", str(tmp_path))

    r = import_common.update_artifact_meta(upload_id, llm_db="not-a-url")
    assert r["ok"] is False
    assert "http" in r["error"]


def test_effective_yang_url_prefers_override():
    import fileserver

    auto = "https://eda-asvr/ns/schemaprofiles/auto/auto.zip"
    override = "https://eda-asvr/ns/schemaprofiles/custom/custom.zip"
    assert fileserver._effective_yang_url(auto, override) == override
    assert fileserver._effective_yang_url(auto, "") == auto
    assert fileserver._effective_yang_url("", override) == override


def test_nodeprofile_yaml_includes_llm_db():
    import fileserver

    yaml = fileserver._nodeprofile_yaml(
        "srl", "26.3.1", "eda", "prof",
        [("images/x.bin", "images/x.md5")],
        "https://yang.example/y.zip",
        llm_db="https://llm.example/db.tar.gz",
    )
    assert "llmDb: https://llm.example/db.tar.gz" in yaml
    assert "yang: https://yang.example/y.zip" in yaml
