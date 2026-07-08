# Security notes (auth trust boundaries)

This app provides an upload UI and a small controller in-cluster, but it relies on EDA’s
Keycloak-based SSO. The security model is about which hop validates which part of the
identity chain.

## Trust boundary hops

1. **Browser → EDA identity proxy (OIDC redirect / session cookies)**
   - The browser never “trusts” JWT claims itself.
   - The identity proxy performs the OIDC login with Keycloak and issues **Keycloak/identity
     proxy cookies** scoped to the proxy path.
   - When the browser is already logged into EDA, the identity proxy can return an auth
     code without showing a Keycloak login page (silent SSO).

2. **EDA identity proxy → this app (`auth.py`)**
   - `fileserver.py` redirects the browser to Keycloak via the identity proxy when needed.
   - On `/oauth/callback`, the app receives an auth code and exchanges it for a Keycloak
     access token **server-to-server** (confidential client).
   - For the request path `/core/httpproxy/v1/imagemanager/*`, the app treats **only** the
     presence of identity-proxy cookies as evidence that the parent EDA session is still
     live (logout propagation). The app does *not* treat the app’s own signed session cookie
     as sufficient alone for logout correctness.

3. **`auth.py` → Keycloak (token exchange and token validation)**
   - The server exchanges the auth code for tokens using the confidential Keycloak client
     (`client_secret` fetched from the Keycloak admin API).
   - `auth.py` validates the resulting JWT access token by:
     - Fetching Keycloak **JWKS** (cached with a TTL).
     - Verifying the JWT signature against the JWKS key.
     - Validating `exp`, `iss`, and `aud`/`azp` for the configured client.
     - Rejecting tokens that fail any check (fail closed).

## Session cookie discipline

- On successful token validation and role-based authorization, `auth.py` mints a short-lived
  HttpOnly session cookie (`im_session`) signed with this controller’s process key.
- API requests use `im_session` to authenticate. Logout correctness combines periodic
  `/api/config` probes, `kc-*` localStorage watchers, and a client-side probe of the
  EDA identity proxy Keycloak session iframe (cookies cleared on EDA logout are not sent
  to `/core/httpproxy/v1/imagemanager` paths).

