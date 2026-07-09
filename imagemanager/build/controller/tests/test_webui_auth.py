"""Smoke tests for embedded SPA auth/session patterns in webui.INDEX_HTML."""

from __future__ import annotations

import webui


def test_bootstrap_validates_keycloak_before_auth_ready():
    html = webui.INDEX_HTML
    assert "function validateBootstrapSession" in html
    assert "ensureKeycloakSessionValid" in html
    bootstrap = html.split("function applyConfigResponse", 1)[1]
    before_auth_ready = bootstrap.split("onAuthReady", 1)[0]
    assert "validateBootstrapSession" in before_auth_ready
    assert "onAuthReady(c.user" not in before_auth_ready


def test_reconcile_uses_keycloak_check():
    html = webui.INDEX_HTML
    reconcile = html.split("function reconcileAuthState", 1)[1].split("function stopSessionWatchers", 1)[0]
    assert "ensureKeycloakSessionValid" in reconcile


def test_identity_probe_gated_on_auth_ready():
    html = webui.INDEX_HTML
    assert "if(!authReady) return true" in html
    assert "probeEdaIdentitySession().then(function(idpOk)" in html


def test_periodic_session_revalidation_interval():
    assert "SESSION_CHECK_MS = 3000" in webui.INDEX_HTML


def test_bootstrap_401_runs_keycloak_silent_sso():
    html = webui.INDEX_HTML
    assert "function handleBootstrap401()" in html
    assert "runSilentSsoAndExchange()" in html
    assert "finishConfigBootstrap()" in html


def test_keycloak_js_and_silent_sso_assets():
    html = webui.INDEX_HTML
    assert "/assets/keycloak.min.js" in html
    assert "/oauth/silent-check-sso.html" in html
    assert "KEYCLOAK_CLIENT_ID = \"auth\"" in html
    assert "exchangeKeycloakSession" in html
    assert 'api("/oauth/session")' in html


def test_confirmed_session_loss_redirects_standalone_to_eda_login():
    html = webui.INDEX_HTML
    assert "function showConfirmedSessionLoss" in html
    assert "redirectToEdaLogin" in html
    assert 'window.location.origin + "/"' in html


def test_embedded_sign_in_banner_uses_keycloak_login():
    html = webui.INDEX_HTML
    assert 'id="authSignInBtn">Sign in</button>' in html
    assert "startKeycloakLogin" in html


def test_navigate_to_stays_in_frame():
    html = webui.INDEX_HTML
    assert "window.top.location" not in html


def test_identity_probe_uses_eda_proxy_not_imagemanager_origin():
    html = webui.INDEX_HTML
    assert "/core/proxy/v1/identity/realms/eda/protocol/openid-connect/login-status-iframe" in html
    assert "if(r.status === 403) return true" in html
    assert "probeEdaOidcSilent" in html
    assert "prompt=none" in html
    assert 'encodeURIComponent(window.location.origin + "/")' in html


def test_bootstrap_auth_has_timeouts_and_guaranteed_exit():
    html = webui.INDEX_HTML
    assert "promiseWithTimeout" in html
    assert "KC_INIT_TIMEOUT_MS = 8000" in html
    assert "BOOTSTRAP_AUTH_TIMEOUT_MS = 20000" in html
    assert "KC_SCRIPT_LOAD_TIMEOUT_MS = 10000" in html
    bootstrap = html.split("function applyConfigResponse", 1)[1]
    assert "bootstrap session validation failed" in bootstrap
    assert "handleBootstrap401()" in bootstrap


def test_keycloak_script_load_deduped():
    html = webui.INDEX_HTML
    assert "keycloakScriptPromise" in html
    assert "window.Keycloak missing" in html


    html = webui.INDEX_HTML
    assert 'data-goto="url-import">Start a URL import' in html
    assert "document.body.addEventListener(\"click\", function(e){" in html
    assert "focusUrlImportForm" in html
