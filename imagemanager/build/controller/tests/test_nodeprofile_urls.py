"""Tests for NodeProfile URL construction and YAML emission."""

from __future__ import annotations

import artifact
import fileserver


def test_asvr_public_base_url():
    assert artifact.asvr_public_base_url("eda-system") == (
        "https://eda-asvr.eda-system.svc/eda-system/"
    )


def test_yang_public_url_sros():
    url = artifact.yang_public_url(
        "eda-system", "sros-ghcr-24.10.r7", "sros-24.10.r7.zip", "eda-system"
    )
    assert url == (
        "https://eda-asvr.eda-system.svc/eda-system/schemaprofiles/"
        "sros-ghcr-24.10.r7/sros-24.10.r7.zip"
    )


def test_yang_public_url_srl():
    url = artifact.yang_public_url(
        "eda", "srlinux-26.3.2", "srlinux-26.3.2.zip", "eda-system"
    )
    assert url == (
        "https://eda-asvr.eda-system.svc/eda/schemaprofiles/"
        "srlinux-26.3.2/srlinux-26.3.2.zip"
    )


def test_llm_db_public_url_sros():
    assert artifact.llm_embedding_basename("sros", "24.10.r7") == (
        "llm-embeddings-sros-24-10-r7.tar.gz"
    )
    url = artifact.llm_db_public_url(
        "eda-system", "sros-ghcr-24.10.r7", "sros", "24.10.r7", "eda-system"
    )
    assert url == (
        "https://eda-asvr.eda-system.svc/eda-system/llm-dbs/"
        "llm-db-sros-ghcr-24.10.r7/llm-embeddings-sros-24-10-r7.tar.gz"
    )


def test_llm_db_public_url_srl():
    assert artifact.llm_embedding_basename("srl", "26.3.2") == (
        "llm-embeddings-srlinux-26-3-2.tar.gz"
    )


def test_suggested_yang_from_meta():
    meta = {
        "displayName": "sros-ghcr-24.10.r7",
        "nos": "sros",
        "version": "24.10.r7",
        "yang": {"filePath": "sros-24.10.r7.zip"},
    }
    url = fileserver._suggested_yang_url(meta, "eda-system")
    assert "schemaprofiles/sros-ghcr-24.10.r7/sros-24.10.r7.zip" in url


def test_resolve_llm_db_prefers_override():
    meta = {
        "displayName": "sros-ghcr-24.10.r7",
        "nos": "sros",
        "version": "24.10.r7",
    }
    custom = "https://example/custom.tar.gz"
    assert fileserver._resolve_llm_db_for_nodeprofile(meta, custom, "eda-system") == custom


def test_resolve_llm_db_auto_when_empty():
    meta = {
        "displayName": "sros-ghcr-24.10.r7",
        "nos": "sros",
        "version": "24.10.r7",
    }
    url = fileserver._resolve_llm_db_for_nodeprofile(meta, None, "eda-system")
    assert "llm-dbs/llm-db-sros-ghcr-24.10.r7/" in url
    assert url.endswith("llm-embeddings-sros-24-10-r7.tar.gz")


def test_nodeprofile_yaml_folded_urls():
    yang = (
        "https://eda-asvr.eda-system.svc/eda-system/schemaprofiles/"
        "sros-ghcr-24.10.r7/sros-24.10.r7.zip"
    )
    llm = (
        "https://eda-asvr.eda-system.svc/eda-system/llm-dbs/"
        "llm-db-sros-ghcr-24.10.r7/llm-embeddings-sros-24-10-r7.tar.gz"
    )
    yaml = fileserver._nodeprofile_yaml(
        "sros",
        "24.10.r7",
        "eda-telemetry",
        "sros-ghcr-24.10.r7",
        [("eda-system/srosimages/sros-24.10.r7", "eda-system/srosimages/sros-24.10.r7-md5")],
        yang,
        license_cm="sros-ghcr-24.10.r7-license",
        llm_db=llm,
    )
    assert "license: sros-ghcr-24.10.r7-license" in yaml
    assert "  llmDb: >-" in yaml
    assert "    " + llm in yaml
    assert "  yang: >-" in yaml
    assert "    " + yang in yaml
    assert "operatingSystem: sros" in yaml
    assert "version: 24.10.r7" in yaml
    assert "eda.nokia.com/bootstrap: 'true'" in yaml
    assert "annotate:" not in yaml


def test_snippet_field_folded():
    url = "https://eda-asvr.eda-system.svc/eda-system/schemaprofiles/p/z.zip"
    assert fileserver._snippet_field("yang", url) == f"yang: >-\n  {url}"
