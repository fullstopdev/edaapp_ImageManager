"""Smoke tests for embedded SPA auth/session patterns in webui.INDEX_HTML."""

from __future__ import annotations

import webui


def test_bootstrap_validates_keycloak_before_auth_ready():
    html = webui.INDEX_HTML
    assert "function validateBootstrapSession" in html
    assert "ensureKeycloakSessionValid" in html
    fast = html.split("function applyConfigResponseFast", 1)[1].split("function ", 1)[0]
    before_auth_ready = fast.split("onAuthReady", 1)[0]
    assert "validateBootstrapSession" not in before_auth_ready
    bg = html.split("function backgroundValidateSession", 1)[1].split("function ", 1)[0]
    assert "validateBootstrapSession" in bg
    assert "onAuthReady" not in bg.split("validateBootstrapSession", 1)[0]


def test_bootstrap_fast_path_shows_ui_before_session_check():
    html = webui.INDEX_HTML
    fast = html.split("function applyConfigResponseFast", 1)[1].split("function ", 1)[0]
    assert "bootDone()" in fast
    assert "startDataLoads" in fast
    bg = html.split("function backgroundValidateSession", 1)[1].split("function ", 1)[0]
    assert "Checking session" in bg


def test_bootstrap_runs_config_before_keycloak_prelude():
    html = webui.INDEX_HTML
    boot = html.split("// ---------- config + namespaces", 1)[1].split("// ---------- file selection", 1)[0]
    assert "runConfigBootstrap()" in boot
    run_boot = html.split("function runConfigBootstrap", 1)[1].split("function handleInitialConfigResponse", 1)[0]
    assert 'fetchJson(api("/api/config"))' in run_boot
    assert "hasKeycloakCallback()" in run_boot
    prelude = html.split("function bootstrapKeycloakPrelude", 1)[1].split("function applyConfigUi", 1)[0]
    assert "login-required" in prelude
    assert "check-sso" not in prelude


def test_bootstrap_keycloak_prelude_is_non_fatal():
    html = webui.INDEX_HTML
    prelude = html.split("function bootstrapKeycloakPrelude", 1)[1].split("function applyConfigUi", 1)[0]
    assert "keycloak bootstrap prelude failed" in prelude
    assert "return null" in prelude


def test_bootstrap_auth_has_timeouts_and_guaranteed_exit():
    html = webui.INDEX_HTML
    assert "promiseWithTimeout" in html
    assert "KC_INIT_TIMEOUT_MS = 5000" in html
    assert "BOOTSTRAP_AUTH_TIMEOUT_MS = 12000" in html
    assert "KC_SCRIPT_LOAD_TIMEOUT_MS = 6000" in html
    assert "SIGNIN_SILENT_SSO_TIMEOUT_MS = 10000" in html
    assert "background session validation failed" in html
    assert "handleBootstrap401()" in html


def test_fresh_sign_in_skips_background_validate():
    html = webui.INDEX_HTML
    assert "function markFreshSignIn" in html
    assert "function maybeBackgroundValidateSession" in html
    assert "skipBackgroundSessionCheck" in html
    h401 = html.split("function handleBootstrap401", 1)[1].split("function showFatal", 1)[0]
    assert "markFreshSignIn()" in h401
    oauth = html.split("function runConfigBootstrap", 1)[1].split("function handleInitialConfigResponse", 1)[0]
    assert "if(exchanged) markFreshSignIn()" in oauth
    finish = html.split("function finishConfigBootstrap", 1)[1].split("function handleInitialConfigResponse", 1)[0]
    assert "maybeBackgroundValidateSession(c)" in finish


def test_keycloak_script_preloaded_in_head():
    html = webui.INDEX_HTML
    assert 'rel="preload"' in html
    assert "keycloak.min.js" in html.split("</head>", 1)[0]


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
    assert "function handleBootstrap401(" in html
    assert "runSilentSsoAndExchange(" in html
    assert "finishConfigBootstrap()" in html
    h401 = html.split("function handleBootstrap401", 1)[1].split("function showFatal", 1)[0]
    assert "attemptEmbeddedSilentSignIn" in h401
    embedded = html.split("function attemptEmbeddedSilentSignIn", 1)[1].split("function markFreshSignIn", 1)[0]
    assert "EMBEDDED_SLOW_HINT_MS" in embedded
    assert "showSignInBanner" in embedded


def test_embedded_early_sso_when_eda_session_likely():
    html = webui.INDEX_HTML
    assert "function edaSessionLikelyPresent" in html
    assert "function attemptEmbeddedSilentSignIn" in html
    boot = html.split("function runConfigBootstrap", 1)[1].split("function handleInitialConfigResponse", 1)[0]
    assert "edaSessionLikelyPresent()" in boot
    assert "earlySso" in boot
    assert "EMBEDDED_EARLY_SSO_TIMEOUT_MS" in boot
    begin = html.split("function beginOAuthSignIn", 1)[1].split("function showConfirmedSessionLoss", 1)[0]
    assert "edaSessionLikelyPresent()" in begin
    assert "attemptEmbeddedSilentSignIn" in begin
    loss = html.split("function showConfirmedSessionLoss", 1)[1].split("function onIdentityProbeFailed", 1)[0]
    assert "edaSessionLikelyPresent()" in loss


def test_embedded_sign_in_banner_only_after_sso_fails():
    html = webui.INDEX_HTML
    embedded = html.split("function attemptEmbeddedSilentSignIn", 1)[1].split("function markFreshSignIn", 1)[0]
    assert 'setAuthBanner("loading", "Signing in' in embedded
    # Sign-in banner with buttons only after SSO failure, not during attempt.
    assert embedded.index("showSignInBanner") > embedded.index("runSilentSsoAndExchange")


def test_keycloak_js_and_silent_sso_assets():
    html = webui.INDEX_HTML
    assert "/assets/keycloak.min.js" in html
    assert 'KEYCLOAK_CLIENT_ID = "auth"' in html
    assert "exchangeKeycloakSession" in html
    assert 'api("/oauth/session")' in html


def test_keycloak_uses_app_path_silent_sso_and_login_redirect():
    html = webui.INDEX_HTML
    assert "function loginRedirectUri" in html
    assert "function silentCheckSsoUri" in html
    assert "function stripOAuthQueryParams" in html
    silent = html.split("function silentCheckSsoUri", 1)[1].split("function ", 1)[0]
    redirect = html.split("function keycloakRedirectUri", 1)[1].split("function ", 1)[0]
    assert 'apiBase + "/oauth/silent-check-sso.html"' in silent
    assert "loginRedirectUri()" in redirect
    assert "checkLoginIframe: !embedded" in html


def test_interactive_sign_in_uses_keycloak_login_with_server_fallback():
    html = webui.INDEX_HTML
    login_fn = html.split("function startKeycloakLogin", 1)[1].split("function fetchJson", 1)[0]
    assert "keycloak.login({" in login_fn
    assert "loginRedirectUri()" in login_fn
    assert "redirectToOAuthLogin();" in login_fn


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


def test_keycloak_script_load_deduped():
    html = webui.INDEX_HTML
    assert "keycloakScriptPromise" in html
    assert "window.Keycloak missing" in html


def test_config_bootstrap_actionable_errors():
    html = webui.INDEX_HTML
    assert "function configBootstrapErrorMessage" in html
    assert "controller is unreachable" in html
    assert "configBootstrapErrorMessage(err, status)" in html


def test_api_calls_attach_bearer_token():
    html = webui.INDEX_HTML
    assert "function authHeaders" in html
    assert "function withAuth" in html
    assert "function applyXhrAuth" in html


def test_url_import_empty_state_navigation():
    html = webui.INDEX_HTML
    assert 'data-goto="url-import">Start a URL import' in html
    assert "document.body.addEventListener(\"click\", function(e){" in html
    assert "focusUrlImportForm" in html
