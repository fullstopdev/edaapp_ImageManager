"""Unit tests for auth.py pure-logic helpers."""

from __future__ import annotations

import time

import auth
import pytest


@pytest.fixture(autouse=True)
def _clear_idp_state_cache():
    auth._idp_state_cache.clear()
    yield
    auth._idp_state_cache.clear()


def test_decode_jwt_roundtrip(make_jwt):
    payload = {"sub": "user1", "preferred_username": "alice", "exp": int(time.time()) + 3600}
    token = make_jwt(payload)
    decoded = auth._decode_jwt(token)
    assert decoded["preferred_username"] == "alice"


def test_token_identity_expired(make_jwt):
    token_resp = {"access_token": make_jwt({"exp": int(time.time()) - 10, "sub": "x"})}
    user, roles = auth.token_identity(token_resp)
    assert user is None
    assert roles == set()


def test_token_identity_rejects_wrong_issuer(make_jwt):
    token_resp = {
        "access_token": make_jwt({
            "iss": "https://example.invalid/issuer",
            "exp": int(time.time()) + 3600,
            "sub": "x",
        }),
    }
    user, roles = auth.token_identity(token_resp)
    assert user is None
    assert roles == set()


def test_token_identity_accepts_same_realm_issuer(make_jwt):
    token_resp = {
        "access_token": make_jwt({
            "iss": "https://example.invalid/realms/eda",
            "exp": int(time.time()) + 3600,
            "sub": "x",
        }),
    }
    user, roles = auth.token_identity(token_resp)
    assert user == "x"
    assert roles == set()


def test_token_identity_rejects_wrong_audience(make_jwt):
    token_resp = {
        "access_token": make_jwt({
            "aud": "wrong-audience",
            "azp": "wrong-azp",
            "exp": int(time.time()) + 3600,
            "sub": "x",
        }),
    }
    user, roles = auth.token_identity(token_resp)
    assert user is None
    assert roles == set()


def test_bearer_token_identity_accepts_auth_client(make_jwt):
    token = make_jwt({
        "aud": auth.BROWSER_CLIENT_ID,
        "azp": auth.BROWSER_CLIENT_ID,
        "exp": int(time.time()) + 3600,
        "preferred_username": "carol",
        "realm_access": {"roles": ["edarole_system-administrator"]},
    })
    user, roles = auth.bearer_token_identity(token)
    assert user == "carol"
    assert "edarole_system-administrator" in roles


def test_bearer_token_identity_rejects_unknown_client(make_jwt):
    token = make_jwt({
        "aud": "other-client",
        "azp": "other-client",
        "exp": int(time.time()) + 3600,
        "sub": "x",
    })
    user, roles = auth.bearer_token_identity(token)
    assert user is None
    assert roles == set()


def test_token_identity_roles(make_jwt):
    token_resp = {
        "access_token": make_jwt({
            "exp": int(time.time()) + 3600,
            "preferred_username": "bob",
            "realm_access": {"roles": ["edarole_system-administrator", "viewer"]},
        }),
    }
    user, roles = auth.token_identity(token_resp)
    assert user == "bob"
    assert "edarole_system-administrator" in roles


def test_is_allowed(monkeypatch):
    monkeypatch.setenv("ALLOWED_ROLES", "imagemanager-viewer,system-administrator")
    assert auth.is_allowed({"edarole_system-administrator"}) is True
    assert auth.is_allowed({"imagemanager-viewer"}) is True
    assert auth.is_allowed({"guest"}) is False


def test_jwt_exp_and_session_cookie_max_age(make_jwt):
    exp = int(time.time()) + 7200
    token = make_jwt({"exp": exp})
    assert auth.jwt_exp(token) == exp
    assert auth.session_cookie_max_age(exp) == auth.SESSION_TTL


def test_has_idp_session_cookie():
    assert auth.has_idp_session_cookie("AUTH_SESSION_ID=abc; other=1") is True
    assert auth.has_idp_session_cookie("foo=bar") is False
    assert auth.has_idp_session_cookie("") is False


def test_verify_session_without_idp_cookies():
    """im_session must validate without Keycloak cookies on the httpproxy path."""
    cookie = auth.make_session("alice")
    assert auth.verify_session(cookie, "foo=bar") == "alice"
    assert auth.verify_session(cookie, "") == "alice"


def test_validate_bearer_token_active_rejects_401(monkeypatch):
    import urllib.error

    monkeypatch.setattr(auth, "_kc_ssl_ctx", lambda: None)

    def _raise_401(*_a, **_kw):
        raise urllib.error.HTTPError("http://x", 401, "unauthorized", {}, None)

    monkeypatch.setattr(auth.urllib.request, "urlopen", _raise_401)
    assert auth.validate_bearer_token_active("tok") is False


def test_validate_bearer_token_active_accepts_ok(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(auth, "_kc_ssl_ctx", lambda: None)
    monkeypatch.setattr(auth.urllib.request, "urlopen", lambda *_a, **_kw: _Resp())
    assert auth.validate_bearer_token_active("tok") is True


# --------------------------- EDA logout detection ---------------------------


def test_make_session_records_the_sso_session():
    """The cookie must remember its Keycloak session, or logout can't be detected."""
    cookie = auth.make_session("alice", sub="user-uuid", sid="sess-1")
    payload = auth.session_payload(cookie)
    assert payload["u"] == "alice"
    assert payload["s"] == "user-uuid"
    assert payload["sid"] == "sess-1"


def test_token_session_ids_prefers_sid_then_session_state(make_jwt):
    with_sid = make_jwt({"sub": "u1", "sid": "s1", "session_state": "legacy"})
    assert auth.token_session_ids(with_sid) == ("u1", "s1")
    legacy = make_jwt({"sub": "u1", "session_state": "legacy"})
    assert auth.token_session_ids(legacy) == ("u1", "legacy")


def test_session_idp_state_active_while_sso_session_lives(monkeypatch):
    monkeypatch.setattr(auth, "_live_session_ids", lambda sub: {"sess-1", "sess-2"})
    cookie = auth.make_session("alice", sub="user-uuid", sid="sess-1")
    assert auth.session_idp_state(cookie) == auth.IDP_ACTIVE


def test_session_idp_state_ended_after_eda_logout(monkeypatch):
    monkeypatch.setattr(auth, "_live_session_ids", lambda sub: set())
    cookie = auth.make_session("alice", sub="user-uuid", sid="sess-1")
    assert auth.session_idp_state(cookie) == auth.IDP_ENDED


def test_session_idp_state_ended_when_only_other_sessions_remain(monkeypatch):
    monkeypatch.setattr(auth, "_live_session_ids", lambda sub: {"other-sess"})
    cookie = auth.make_session("alice", sub="user-uuid", sid="sess-1")
    assert auth.session_idp_state(cookie) == auth.IDP_ENDED


def test_session_idp_state_active_without_sid_when_user_has_a_session(monkeypatch):
    monkeypatch.setattr(auth, "_live_session_ids", lambda sub: {"whatever"})
    cookie = auth.make_session("alice", sub="user-uuid")
    assert auth.session_idp_state(cookie) == auth.IDP_ACTIVE


def test_session_idp_state_unknown_when_keycloak_is_unreachable(monkeypatch):
    """A Keycloak blip must never sign anyone out — it has to fail open."""
    def _boom(_sub):
        raise OSError("connection refused")

    monkeypatch.setattr(auth, "_live_session_ids", _boom)
    cookie = auth.make_session("alice", sub="user-uuid", sid="sess-1")
    assert auth.session_idp_state(cookie) == auth.IDP_UNKNOWN


def test_session_idp_state_unknown_when_admin_api_refuses(monkeypatch):
    import urllib.error

    def _forbidden(_sub):
        raise urllib.error.HTTPError("http://kc", 403, "forbidden", {}, None)

    monkeypatch.setattr(auth, "_live_session_ids", _forbidden)
    cookie = auth.make_session("alice", sub="user-uuid", sid="sess-1")
    assert auth.session_idp_state(cookie) == auth.IDP_UNKNOWN


def test_session_idp_state_ended_when_realm_user_is_gone(monkeypatch):
    import urllib.error

    def _missing(_sub):
        raise urllib.error.HTTPError("http://kc", 404, "not found", {}, None)

    monkeypatch.setattr(auth, "_live_session_ids", _missing)
    cookie = auth.make_session("alice", sub="user-uuid", sid="sess-1")
    assert auth.session_idp_state(cookie) == auth.IDP_ENDED


def test_session_idp_state_unknown_for_cookie_without_sso_session(monkeypatch):
    """Cookies minted before this feature have nothing to check, so fail open."""
    monkeypatch.setattr(auth, "_live_session_ids", lambda sub: set())
    assert auth.session_idp_state(auth.make_session("alice")) == auth.IDP_UNKNOWN


def test_session_idp_state_ended_for_invalid_cookie():
    assert auth.session_idp_state("") == auth.IDP_ENDED
    assert auth.session_idp_state("garbage.signature") == auth.IDP_ENDED


def test_session_idp_state_is_cached(monkeypatch):
    """A UI polling every few seconds must not mean a Keycloak call per poll."""
    calls = []

    def _count(sub):
        calls.append(sub)
        return {"sess-1"}

    monkeypatch.setattr(auth, "_live_session_ids", _count)
    cookie = auth.make_session("alice", sub="user-uuid", sid="sess-1")
    for _ in range(5):
        assert auth.session_idp_state(cookie) == auth.IDP_ACTIVE
    assert len(calls) == 1


def test_unknown_session_state_is_cached_briefly(monkeypatch):
    def _boom(_sub):
        raise OSError("down")

    monkeypatch.setattr(auth, "_live_session_ids", _boom)
    assert auth.keycloak_session_state("user-uuid", "sess-1") == auth.IDP_UNKNOWN
    cached = auth._idp_state_cache[("user-uuid", "sess-1")]
    assert cached[1] - time.time() <= auth._IDP_UNKNOWN_TTL_SECONDS + 1
