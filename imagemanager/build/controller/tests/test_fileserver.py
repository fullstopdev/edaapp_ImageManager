"""Unit tests for fileserver.py pure-logic helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import auth
import fileserver
import pytest


@pytest.fixture(autouse=True)
def _clear_idp_state_cache():
    auth._idp_state_cache.clear()
    yield
    auth._idp_state_cache.clear()


def _request(cookie="", authorization=""):
    """Build a Handler with just enough state to exercise the auth gate (no socket)."""
    handler = fileserver.Handler.__new__(fileserver.Handler)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if authorization:
        headers["Authorization"] = authorization
    handler.headers = headers
    return handler


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


# --------------------------- EDA logout detection ---------------------------


def _session_cookie(user="alice", sub="user-uuid", sid="sess-1"):
    return f"{auth.SESSION_COOKIE}={auth.make_session(user, sub=sub, sid=sid)}"


def test_session_state_active_while_eda_session_lives(monkeypatch):
    monkeypatch.setattr(auth, "_live_session_ids", lambda sub: {"sess-1"})
    assert _request(_session_cookie())._session_state() == ("alice", auth.IDP_ACTIVE)


def test_session_state_ended_after_eda_logout(monkeypatch):
    """A signed, unexpired cookie is not enough once Keycloak dropped the session."""
    monkeypatch.setattr(auth, "_live_session_ids", lambda sub: set())
    user, reason = _request(_session_cookie())._session_state()
    assert user is None
    assert reason == auth.IDP_ENDED


def test_session_state_keeps_user_when_keycloak_is_unreachable(monkeypatch):
    def _boom(_sub):
        raise OSError("connection refused")

    monkeypatch.setattr(auth, "_live_session_ids", _boom)
    assert _request(_session_cookie())._session_state() == ("alice", auth.IDP_ACTIVE)


def test_session_state_expired_without_a_cookie():
    user, reason = _request()._session_state()
    assert user is None
    assert reason == "expired"


def test_serve_session_reports_state(monkeypatch):
    sent = {}
    handler = _request()
    monkeypatch.setattr(
        type(handler), "_send_json",
        lambda self, obj, code=200: sent.update(body=obj, code=code), raising=False)

    handler._serve_session("alice", auth.IDP_ACTIVE)
    assert sent == {"body": {"ok": True, "user": "alice", "state": "active"}, "code": 200}

    handler._serve_session(None, auth.IDP_ENDED)
    assert sent == {"body": {"ok": False, "state": "ended"}, "code": 401}


def test_nos_label_and_infer():
    assert fileserver.nos_label("srl") == "Nokia SR Linux"
    assert fileserver.nos_label("sros") == "Nokia SR OS"
    assert fileserver.nos_label("") == ""
    import artifact

    assert fileserver._infer_nos_from_repo(artifact.SROS_REPO) == "sros"
    assert fileserver._infer_nos_from_repo("images") == "srl"
