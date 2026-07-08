"""Unit tests for fileserver.py pure-logic helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import fileserver


def test_within_upload_grace_recent_timestamp(monkeypatch):
    monkeypatch.setattr(fileserver, "_UPLOAD_FAILURE_GRACE_SECONDS", 120)
    recent = datetime.now(UTC).isoformat(timespec="seconds")
    assert fileserver._within_upload_grace(recent) is True
    old = (datetime.now(UTC) - timedelta(seconds=300)).isoformat(timespec="seconds")
    assert fileserver._within_upload_grace(old) is False
    assert fileserver._within_upload_grace("") is False


def test_resolve_download_status_local_available():
    st, reason = fileserver._resolve_download_status(
        True, {"downloadStatus": "Available", "statusReason": ""})
    assert st == "Available"


def test_resolve_download_status_local_ok_cr_error_in_grace():
    st, _ = fileserver._resolve_download_status(
        True, {"downloadStatus": "Error"}, in_upload_grace=True)
    assert st == "InProgress"


def test_resolve_download_status_asvr_only():
    st, reason = fileserver._resolve_download_status(
        False, {"downloadStatus": "Available"})
    assert st == "AsvrOnly"
    assert "eda-asvr" in reason


def test_aggregate_download_status_worst_case():
    st, _ = fileserver._aggregate_download_status(
        ["Available", "Error"], ["", "pull failed"])
    assert st == "Error"
    st, _ = fileserver._aggregate_download_status(["AsvrOnly", "Available"], ["", ""])
    assert st == "AsvrOnly"
    st, _ = fileserver._aggregate_download_status(["Available", "Available"], ["", ""])
    assert st == "Available"


def test_nos_label_and_infer():
    assert fileserver.nos_label("srl") == "Nokia SR Linux"
    assert fileserver.nos_label("sros") == "Nokia SR OS"
    assert fileserver.nos_label("") == ""
    import artifact

    assert fileserver._infer_nos_from_repo(artifact.SROS_REPO) == "sros"
    assert fileserver._infer_nos_from_repo("images") == "srl"
