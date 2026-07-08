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
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

import k8s

logger = logging.getLogger("auth")

POD_NAMESPACE = os.environ.get("POD_NAMESPACE", "eda-system")
REALM = "eda"
CLIENT_ID = "eda"
# Public browser client for RP-initiated logout (same as EDA GUI / cable-map).
BROWSER_CLIENT_ID = "auth"
# Browser-facing authorize URL goes through EDA's identity proxy — the SAME
# Keycloak base the EDA GUI logs in through — so an already-logged-in EDA user
# is 302'd back with a code and never sees a login form (seamless SSO in the
# embedded panel). Server-to-server calls below still use KC_PROXY_PATH.
IDENTITY_PROXY_PATH = "/core/proxy/v1/identity"
KC_PROXY_PATH = "/core/httpproxy/v1/keycloak"
# In-cluster Keycloak (server-to-server: admin token, client-secret, code exchange).
KC_INTERNAL_BASE = f"https://eda-api.{POD_NAMESPACE}.svc{KC_PROXY_PATH}"
APP_PROXY_PREFIX = "/core/httpproxy/v1/imagemanager"
CALLBACK_SUBPATH = "/oauth/callback"

SESSION_COOKIE = "im_session"
STATE_COOKIE = "im_oauth_state"
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
_jwks_cache = {"keys": None, "exp": 0.0}
_jwks_lock = threading.Lock()

_ISSUER_ENV = "JWT_ISSUER"
_DEFAULT_JWT_ISSUER = f"{KC_INTERNAL_BASE}/realms/{REALM}"
JWT_ISSUER = os.environ.get(_ISSUER_ENV, "") or _DEFAULT_JWT_ISSUER
_JWKS_TTL_SECONDS = int(os.environ.get("JWKS_CACHE_TTL_SECONDS", "300"))
_JWT_LEEWAY_SECONDS = int(os.environ.get("JWT_LEEWAY_SECONDS", "5"))
_IDP_SESSION_COOKIE_NAMES = (
    "KEYCLOAK_SESSION",
    "KEYCLOAK_IDENTITY",
    "AUTH_SESSION_ID",
    "AUTH_SESSION_ID_LEGACY",
    "KC_RESTART",
)


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


def _client_secret(force=False):
    if _secret_cache[0] and not force:
        return _secret_cache[0]
    admin = _kc_admin_token()
    hdr = {"Authorization": f"Bearer {admin}"}
    clients = _get_json(
        f"{KC_INTERNAL_BASE}/admin/realms/{REALM}/clients?clientId={CLIENT_ID}", hdr)
    if not clients:
        raise RuntimeError(f"Keycloak client '{CLIENT_ID}' not found")
    uuid = clients[0]["id"]
    cs = _get_json(
        f"{KC_INTERNAL_BASE}/admin/realms/{REALM}/clients/{uuid}/client-secret", hdr)
    _secret_cache[0] = cs["value"]
    return _secret_cache[0]


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


def identity_base(headers):
    """Browser-facing Keycloak base URL (EDA identity proxy)."""
    return external_base(headers) + IDENTITY_PROXY_PATH


def authorize_url(headers, state):
    base = external_base(headers)
    q = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": redirect_uri(headers),
        "state": state,
    })
    # Identity proxy (not KC_PROXY_PATH): its Keycloak session cookie matches the
    # EDA GUI's, so an already-logged-in user is admitted with no login form.
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


def _jwks_url():
    return f"{KC_INTERNAL_BASE}/realms/{REALM}/protocol/openid-connect/certs"


def _fetch_jwks():
    """Fetch Keycloak JWKS (not cached)."""
    return _get_json(_jwks_url())


def _jwks_keys(force=False):
    """Return JWKS keys list with TTL caching."""
    now = time.time()
    with _jwks_lock:
        if (not force
                and _jwks_cache["keys"] is not None
                and _jwks_cache["exp"] > now):
            return _jwks_cache["keys"]
        jwks = _fetch_jwks() or {}
        keys = jwks.get("keys") or []
        _jwks_cache["keys"] = keys
        _jwks_cache["exp"] = now + _JWKS_TTL_SECONDS
        return keys


def _b64u_to_int(s):
    raw = base64.urlsafe_b64decode(
        (s or "").encode("ascii") + b"=" * (-len(s) % 4)
    )
    return int.from_bytes(raw, "big") if raw else 0


def _validate_jwt_claims(payload):
    if not isinstance(payload, dict):
        return False
    exp = int(payload.get("exp") or 0)
    if not exp:
        return False
    if exp < time.time() - _JWT_LEEWAY_SECONDS:
        return False
    if payload.get("iss") != JWT_ISSUER:
        return False

    aud = payload.get("aud")
    azp = payload.get("azp")
    aud_ok = False
    if isinstance(aud, str) and aud == CLIENT_ID:
        aud_ok = True
    elif isinstance(aud, list) and CLIENT_ID in aud:
        aud_ok = True
    azp_ok = (azp == CLIENT_ID) if azp is not None else False
    return bool(aud_ok or azp_ok)


def _decode_jwt(token):
    """Decode and verify a Keycloak-signed JWT using the realm JWKS.

    Returns the verified payload dict; returns {} if signature/claims fail.
    """
    if not token or "." not in token:
        return {}
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        header_b64 = parts[0]
        header_json = base64.urlsafe_b64decode(
            header_b64 + "=" * (-len(header_b64) % 4)
        ).decode("utf-8", "replace")
        header = json.loads(header_json)
        alg = header.get("alg")
        kid = header.get("kid")
        if not alg or alg == "none":
            return {}

        keys = _jwks_keys()
        jwk = None
        if kid:
            for k in keys:
                if k.get("kid") == kid:
                    jwk = k
                    break
        if not jwk:
            # Fall back to the first RSA key.
            for k in keys:
                if k.get("kty") == "RSA":
                    jwk = k
                    break
        if not jwk or jwk.get("kty") != "RSA":
            return {}

        e = _b64u_to_int(jwk.get("e") or "")
        n = _b64u_to_int(jwk.get("n") or "")
        if not (e and n):
            return {}

        public_key = RSAPublicNumbers(e=e, n=n).public_key()

        # Verify signature only; validate claims explicitly to enforce aud/azp
        # semantics that PyJWT's standard audience check doesn't cover.
        payload = pyjwt.decode(
            token,
            key=public_key,
            algorithms=[alg],
            options={
                "verify_aud": False,
                "verify_exp": False,
                "verify_iss": False,
                "verify_nbf": False,
                "verify_iat": False,
            },
        )
        if not _validate_jwt_claims(payload):
            return {}
        return payload
    except Exception:
        # Never log token contents; failure modes include rotated JWKS,
        # invalid signatures, or mismatched issuer/audience.
        return {}


def token_identity(token_resp):
    """(username, set_of_roles) from a token response, or (None, set())."""
    at = token_resp.get("access_token", "")
    p = _decode_jwt(at)
    if not p:
        return None, set()
    user = p.get("preferred_username") or p.get("sub")
    roles = set((p.get("realm_access") or {}).get("roles") or [])
    return user, roles


def is_allowed(roles):
    allow = allowed_roles()
    for r in allow:
        if r in roles or ("edarole_" + r) in roles:
            return True
    return False


def jwt_exp(access_token):
    """Access-token expiry (unix seconds) from a bearer token, or None."""
    p = _decode_jwt(access_token or "")
    exp = int(p.get("exp", 0) or 0)
    return exp if exp else None


def session_cookie_max_age(token_exp=None):
    """HttpOnly session cookie Max-Age (app session TTL; not access-token bound)."""
    return SESSION_TTL


def has_idp_session_cookie(raw_cookie_header):
    """Whether this request carries Keycloak/identity-proxy session cookies."""
    if not raw_cookie_header:
        return False
    c = SimpleCookie()
    try:
        c.load(raw_cookie_header)
    except Exception:
        return False
    for name in c.keys():
        if name in _IDP_SESSION_COOKIE_NAMES:
            return True
    return False


def end_session_url(headers, post_logout_redirect=None):
    """Browser-facing Keycloak RP-initiated logout."""
    redirect = post_logout_redirect or (external_base(headers) + "/")
    q = urllib.parse.urlencode({
        "client_id": BROWSER_CLIENT_ID,
        "post_logout_redirect_uri": redirect,
    })
    return (identity_base(headers)
            + f"/realms/{REALM}/protocol/openid-connect/logout?{q}")


def eda_login_url(headers):
    """EDA GUI root — the login page after a full sign-out."""
    return external_base(headers) + "/"


# --------------------------- signed cookies ---------------------------

def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(body_bytes):
    return _b64u(hmac.new(_SIGNING_KEY, body_bytes, hashlib.sha256).digest())


def make_session(username, token_exp=None):
    payload = {"u": username, "exp": int(time.time()) + SESSION_TTL}
    if token_exp:
        payload["te"] = int(token_exp)
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body.encode('ascii'))}"


def verify_session(cookie, raw_cookie_header=""):
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
    if int(payload.get("exp", 0)) < time.time():
        return None
    # Do not require identity-proxy Keycloak cookies here: they are scoped to
    # /core/proxy/v1/identity and are not sent on /core/httpproxy/v1/imagemanager
    # requests. EDA logout sync is handled client-side (kc-* localStorage watchers).
    return payload.get("u")


def new_state():
    return secrets.token_urlsafe(24)
