"""Smoke tests for embedded SPA auth/session patterns in webui.INDEX_HTML."""

from __future__ import annotations

import webui


def test_bootstrap_trusts_config_without_identity_probe():
    html = webui.INDEX_HTML
    assert "authBootstrapComplete = true" in html
    assert "onAuthReady(c.user" in html
    # Bootstrap must not gate on identity probe (false-negative → OAuth loop).
    bootstrap = html.split("function applyConfigResponse", 1)[1]
    before_probe_fn = bootstrap.split("function probeEdaIdentitySession", 1)[0]
    assert "probeEdaIdentitySession().then(function(idpOk)" not in before_probe_fn


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


def test_url_import_empty_state_navigates_to_import_tab():
    html = webui.INDEX_HTML
    assert 'data-goto="url-import">Start a URL import' in html
    assert "document.body.addEventListener(\"click\", function(e){" in html
    assert "focusUrlImportForm" in html
