"""
EDA single sign-on + role-based authorization (stdlib only).

The UI is gated so only logged-in EDA users who hold one of the allowed EDA
roles may use it. We implement the OIDC Authorization Code (Standard) flow
against EDA's Keycloak — the same flow the EDA GUI uses — so a user already
logged into EDA is admitted with no extra prompt (true SSO).

Flow:
  1. unauthenticated request  -> 302 to Keycloak authorize (external URL)
  2. Keycloak -> 302 back to /oauth/callback?code=...&state=...
  3. exchange code for a token at Keycloak (in-cluster, server-to-server)
  4. read realm_access.roles; if it intersects the allowed roles, mint a signed
     session cookie (~8h); otherwise 403.

Keycloak specifics on this cluster (verified):
  - realm "eda", confidential client "eda" with standardFlowEnabled + redirectUris ['/*']
    (so our callback URL needs no Keycloak change).
  - EDA roles appear in the token as realm_access.roles, e.g.
    "edarole_system-administrator" plus a bare "admin"; groups are unused.
  - The "eda" client secret is fetched via the Keycloak admin API using
    keycloak-admin-secret (same pattern as edaapp_UserAudit).

TLS: the in-cluster Keycloak (via eda-api) is signed by eda-api-ca, which the
internal trust bundle does NOT cover (gotcha 3) — we read the eda-api-ca Secret
and trust it explicitly for server-to-server calls.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import k8s

logger = logging.getLogger("auth")

POD_NAMESPACE = os.environ.get("POD_NAMESPACE", "eda-system")
REALM = "eda"
CLIENT_ID = "eda"
# Public browser client used by keycloak-js for silent SSO inside the EDA GUI
# iframe (same pattern as cable-map.eda.labs).
BROWSER_CLIENT_ID = "auth"
IDENTITY_PROXY_PATH = "/core/proxy/v1/identity"
KC_PROXY_PATH = "/core/httpproxy/v1/keycloak"
# In-cluster Keycloak (server-to-server: admin token, client-secret, code exchange).
KC_INTERNAL_BASE = f"https://eda-api.{POD_NAMESPACE}.svc{KC_PROXY_PATH}"
APP_PROXY_PREFIX = "/core/httpproxy/v1/imagemanager"
CALLBACK_SUBPATH = "/oauth/callback"

SESSION_COOKIE = "im_session"
STATE_COOKIE = "im_oauth_state"
RETURN_COOKIE = "im_oauth_return"
SESSION_TTL = 8 * 3600  # 8 hours
_HTTP_TIMEOUT = 20

# Allowed roles come from the install-time setting (env ALLOWED_ROLES). A user is
# allowed if they hold ANY of them; "X" matches token role "X" or "edarole_X".
ALLOWED_ROLES_ENV = "ALLOWED_ROLES"
DEFAULT_ALLOWED_ROLES = "system-administrator"

# Process-lifetime signing key for session/state cookies (replicas=1, Recreate;
# a restart just forces re-login, which is acceptable).
_SIGNING_KEY = os.urandom(32)

_ca_cache = [None]
_secret_cache = [None]
_admin_tok_cache = {"tok": None, "exp": 0}
_browser_client_cache = {"info": None, "exp": 0}


# --------------------------- config ---------------------------

def allowed_roles():
    raw = os.environ.get(ALLOWED_ROLES_ENV, "") or DEFAULT_ALLOWED_ROLES
    return [r.strip() for r in raw.split(",") if r.strip()] or [DEFAULT_ALLOWED_ROLES]


def enabled():
    """Auth is active whenever we can reach the K8s API for the client secret.
    (Always true in-cluster; kept as a hook for local testing.)"""
    return os.environ.get("IMAGEMANAGER_DISABLE_AUTH") != "1"


# --------------------------- TLS to in-cluster Keycloak ---------------------------

def _eda_api_ca_pem():
    if _ca_cache[0] is None:
        sec = k8s.read_secret("eda-api-ca", POD_NAMESPACE) or {}
        b64 = (sec.get("data") or {}).get("ca.crt", "")
        _ca_cache[0] = base64.b64decode(b64).decode("utf-8") if b64 else ""
    return _ca_cache[0]


def _kc_ssl_ctx():
    pem = _eda_api_ca_pem()
    if pem:
        return ssl.create_default_context(cadata=pem)
    # Fall back to system roots (e.g. eda-api fronted by a publicly-trusted cert).
    return ssl.create_default_context()


def _post_form(url, fields, headers=None):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, context=_kc_ssl_ctx(), timeout=_HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url, headers=None):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, context=_kc_ssl_ctx(), timeout=_HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------- Keycloak client secret ---------------------------

def _kc_admin_token():
    now = time.time()
    if _admin_tok_cache["tok"] and _admin_tok_cache["exp"] > now + 30:
        return _admin_tok_cache["tok"]
    sec = k8s.read_secret("keycloak-admin-secret", POD_NAMESPACE) or {}
    d = sec.get("data") or {}
    user = base64.b64decode(d.get("username", "")).decode("utf-8")
    pw = base64.b64decode(d.get("password", "")).decode("utf-8")
    tok = _post_form(
        f"{KC_INTERNAL_BASE}/realms/master/protocol/openid-connect/token",
        {"grant_type": "password", "client_id": "admin-cli", "username": user, "password": pw},
    )
    _admin_tok_cache["tok"] = tok["access_token"]
    _admin_tok_cache["exp"] = now + int(tok.get("expires_in", 60))
    return _admin_tok_cache["tok"]


def _kc_client_by_id(client_id, admin_hdr):
    """Return the first Keycloak client dict for *client_id*, or None."""
    clients = _get_json(
        f"{KC_INTERNAL_BASE}/admin/realms/{REALM}/clients?clientId={client_id}", admin_hdr)
    return clients[0] if clients else None


def _client_secret(force=False):
    if _secret_cache[0] and not force:
        return _secret_cache[0]
    admin = _kc_admin_token()
    hdr = {"Authorization": f"Bearer {admin}"}
    row = _kc_client_by_id(CLIENT_ID, hdr)
    if not row:
        raise RuntimeError(f"Keycloak client '{CLIENT_ID}' not found")
    cs = _get_json(
        f"{KC_INTERNAL_BASE}/admin/realms/{REALM}/clients/{row['id']}/client-secret", hdr)
    _secret_cache[0] = cs["value"]
    return _secret_cache[0]


def _redirect_uri_covers_proxy(redirect_uris):
    """True when redirect URIs admit our HttpProxy prefix (or wildcard)."""
    prefix = APP_PROXY_PREFIX.rstrip("/")
    for raw in redirect_uris or []:
        u = (raw or "").rstrip("/")
        if u in ("/*", "+"):
            return True
        if u.endswith("/*") and prefix.startswith(u[:-1].rstrip("/")):
            return True
        if u == prefix or prefix.startswith(u + "/") or u.startswith(prefix):
            return True
    return False


def browser_client_info(force=False):
    """Inspect the public ``auth`` client used by keycloak-js (admin API)."""
    now = time.time()
    if _browser_client_cache["info"] and not force and _browser_client_cache["exp"] > now:
        return dict(_browser_client_cache["info"])
    info = {
        "clientId": BROWSER_CLIENT_ID,
        "exists": False,
        "redirectUris": [],
        "webOrigins": [],
        "coversImProxy": False,
    }
    try:
        admin = _kc_admin_token()
        hdr = {"Authorization": f"Bearer {admin}"}
        row = _kc_client_by_id(BROWSER_CLIENT_ID, hdr)
        if row:
            info["exists"] = True
            info["redirectUris"] = list(row.get("redirectUris") or [])
            info["webOrigins"] = list(row.get("webOrigins") or [])
            info["publicClient"] = bool(row.get("publicClient"))
            info["standardFlowEnabled"] = bool(row.get("standardFlowEnabled"))
            info["coversImProxy"] = _redirect_uri_covers_proxy(info["redirectUris"])
    except Exception as e:
        info["error"] = str(e)
        logger.warning("Keycloak browser client '%s' check failed: %s",
                       BROWSER_CLIENT_ID, e)
    _browser_client_cache["info"] = info
    _browser_client_cache["exp"] = now + 300
    return dict(info)


# --------------------------- OIDC flow ---------------------------

def external_base(headers):
    """Browser-facing https://host base, from the proxy's forwarded headers."""
    host = (headers.get("X-Forwarded-Host") or headers.get("Host") or "").split(",")[0].strip()
    proto = (headers.get("X-Forwarded-Proto") or "https").split(",")[0].strip()
    # An explicit override wins (install-time escape hatch); else derive from headers.
    ext = (os.environ.get("EXTERNAL_URL") or "").strip().rstrip("/")
    if ext:
        return ext
    return f"{proto}://{host}" if host else ""


def redirect_uri(headers):
    return external_base(headers) + APP_PROXY_PREFIX + CALLBACK_SUBPATH


def authorize_url(headers, state):
    """Browser-facing authorize URL.

    Uses the EDA identity proxy path — the SAME Keycloak base the EDA GUI logs
    in through. Keycloak session cookies are scoped to the KC base path, so
    only this base sees the user's existing GUI session and can 302 straight
    back with a code (true SSO, no login form). The httpproxy Keycloak path
    (KC_PROXY_PATH) serves the same realm but its cookie path never matches
    the GUI session, which forced a fresh login page.
    """
    base = external_base(headers)
    q = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": redirect_uri(headers),
        "state": state,
    })
    return f"{base}{IDENTITY_PROXY_PATH}/realms/{REALM}/protocol/openid-connect/auth?{q}"


def exchange_code(code, headers):
    """Exchange an auth code for tokens (server-to-server, in-cluster)."""
    fields = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(headers),
        "client_id": CLIENT_ID,
        "client_secret": _client_secret(),
    }
    url = f"{KC_INTERNAL_BASE}/realms/{REALM}/protocol/openid-connect/token"
    try:
        return _post_form(url, fields)
    except urllib.error.HTTPError as e:
        # Secret may have rotated; refetch once and retry.
        if e.code in (400, 401):
            fields["client_secret"] = _client_secret(force=True)
            return _post_form(url, fields)
        raise


def _decode_jwt(token):
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))


def token_identity(token_resp):
    """(username, set_of_roles) from a token response, or (None, set())."""
    return jwt_identity(token_resp.get("access_token", ""))


def jwt_identity(access_token):
    """(username, set_of_roles) from a bearer access token, or (None, set())."""
    p = _decode_jwt(access_token or "")
    if not p:
        return None, set()
    if p.get("exp", 0) < time.time():
        return None, set()
    user = p.get("preferred_username") or p.get("sub")
    roles = set((p.get("realm_access") or {}).get("roles") or [])
    return user, roles


def identity_base(headers):
    """Browser-facing Keycloak base URL for keycloak-js (EDA identity proxy)."""
    return external_base(headers) + IDENTITY_PROXY_PATH


def silent_sso_redirect_uri(headers):
    return external_base(headers) + APP_PROXY_PREFIX + "/oauth/silent-sso.html"


def session_cookie_max_age(token_exp=None):
    """HttpOnly session cookie Max-Age: min(app TTL, remaining access-token life)."""
    if token_exp:
        remaining = int(token_exp) - int(time.time())
        if remaining > 0:
            return min(SESSION_TTL, remaining)
    return SESSION_TTL


def end_session_url(headers, post_logout_redirect=None):
    """Browser-facing Keycloak RP-initiated logout (public ``auth`` client)."""
    redirect = post_logout_redirect or (external_base(headers) + APP_PROXY_PREFIX + "/")
    q = urllib.parse.urlencode({
        "client_id": BROWSER_CLIENT_ID,
        "post_logout_redirect_uri": redirect,
    })
    return (identity_base(headers)
            + f"/realms/{REALM}/protocol/openid-connect/logout?{q}")


def is_allowed(roles):
    allow = allowed_roles()
    for r in allow:
        if r in roles or ("edarole_" + r) in roles:
            return True
    return False


# --------------------------- signed cookies ---------------------------

def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(body_bytes):
    return _b64u(hmac.new(_SIGNING_KEY, body_bytes, hashlib.sha256).digest())


def jwt_exp(access_token):
    """Access-token expiry (unix seconds) from a bearer token, or None."""
    p = _decode_jwt(access_token or "")
    exp = int(p.get("exp", 0) or 0)
    return exp if exp else None


def make_session(username, token_exp=None):
    payload = {"u": username, "exp": int(time.time()) + SESSION_TTL}
    if token_exp:
        payload["te"] = int(token_exp)
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body.encode('ascii'))}"


def verify_session(cookie):
    """Return the username if the session cookie is valid+unexpired, else None."""
    if not cookie or "." not in cookie:
        return None
    body, sig = cookie.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(body.encode("ascii"))):
        return None
    try:
        payload = json.loads(_b64u_dec(body).decode("utf-8"))
    except Exception:
        return None
    now = time.time()
    if int(payload.get("exp", 0)) < now:
        return None
    # Bound session lifetime to the Keycloak access token that minted it.
    if int(payload.get("te", 0)) and int(payload["te"]) < now:
        return None
    return payload.get("u")


def user_from_bearer(headers, session_cookie=""):
    """Username if the request carries a valid session or Keycloak bearer token."""
    if not enabled():
        return "local"
    user = verify_session(session_cookie)
    if user:
        return user
    auth_hdr = headers.get("Authorization", "")
    if auth_hdr.lower().startswith("bearer "):
        token = auth_hdr[7:].strip()
        user, roles = jwt_identity(token)
        if user and is_allowed(roles):
            return user
    return None


def new_state():
    return secrets.token_urlsafe(24)
