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


def test_session_loss_redirects_to_eda_login():
    html = webui.INDEX_HTML
    assert "redirectToEdaLogin" in html
    assert 'window.location.origin + "/"' in html


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
