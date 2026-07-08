"""Unit tests for auth.py pure-logic helpers."""

from __future__ import annotations

import time

import auth


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
