"""Smoke tests for embedded SPA auth/session patterns in webui.INDEX_HTML."""

from __future__ import annotations

import webui


def test_bootstrap_probes_identity_before_auth_ready():
    html = webui.INDEX_HTML
    assert "probeEdaIdentitySession().then(function(idpOk)" in html
    probe_at = html.index("probeEdaIdentitySession().then(function(idpOk)")
    ready_at = html.index("onAuthReady(c.user")
    assert probe_at < ready_at


def test_periodic_session_revalidation_interval():
    assert "SESSION_CHECK_MS = 3000" in webui.INDEX_HTML


def test_bootstrap_401_starts_oauth_not_eda_home():
    html = webui.INDEX_HTML
    assert "function handleBootstrap401()" in html
    assert "beginOAuthSignIn(\"Sign in to use Image Manager.\")" in html
    assert "redirectToOAuthLogin" in html


def test_confirmed_session_loss_redirects_standalone_to_eda_login():
    html = webui.INDEX_HTML
    assert "function showConfirmedSessionLoss" in html
    assert "redirectToEdaLogin" in html
    assert 'window.location.origin + "/"' in html


def test_embedded_sign_in_banner_includes_oauth_button():
    html = webui.INDEX_HTML
    assert 'id="authSignInBtn">Sign in</button>' in html
    assert "redirectToOAuthLogin" in html


def test_navigate_to_stays_in_frame():
    html = webui.INDEX_HTML
    assert "window.top.location" not in html


def test_identity_probe_uses_eda_proxy_not_imagemanager_origin():
    html = webui.INDEX_HTML
    assert "/core/proxy/v1/identity/realms/eda/protocol/openid-connect/login-status-iframe" in html
    assert "if(r.status === 403) return true" in html
    assert "probeEdaOidcSilent" in html
    assert "prompt=none" in html


def test_url_import_empty_state_navigates_to_import_tab():
    html = webui.INDEX_HTML
    assert 'data-goto="url-import">Start a URL import' in html
    assert "document.body.addEventListener(\"click\", function(e){" in html
    assert "focusUrlImportForm" in html
