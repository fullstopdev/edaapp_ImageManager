# Changelog

## v0.0.63

**Fix sign-in failure — wire server OIDC fallback + auth diagnostics:**

- **Root cause:** `redirectToOidcLogin()` (server confidential-client `eda` flow via
  `/oauth/login`) was never called; 100% of sign-in depended on keycloak-js public
  client `auth`. When keycloak-js failed (script, check-sso iframe, or token
  exchange), bootstrap showed *Sign-in failed* with no second path.
- **Server OIDC fallback:** After keycloak-js failure, auto-try `/oauth/login` once
  (guarded like `canAutoKeycloakLogin`). **Sign in** button: `keycloak.login()`
  first, then `/oauth/login` on reject. `return` query round-trips through callback
  → `im_session` cookie → SPA fast path.
- **Diagnostics:** Console logging on auth failures (`authLog`); errors no longer
  swallowed in `.catch()` blocks; Keycloak `onAuthError` / `onAuthRefreshError`;
  `keycloak.min.js` HEAD probe; `?auth_debug=1` enables verbose init logging.
- **Keycloak admin check:** `auth.browser_client_info()` verifies public client
  `auth` exists and redirect URIs cover `/core/httpproxy/v1/imagemanager/*`;
  logged at controller startup and exposed in `/api/config` when authed.
- **v0.0.60 preserved:** 20s bootstrap cap, 8s SSO timeout, unconditional
  `bootDone()` / `hideSignInBanner()` in `finally`.

## v0.0.62

**Fix sign-in failure — silent-sso URL + bootstrap (v0.0.55–61 regression):**

- **Root cause:** `silentCheckSsoRedirectUri` used
  `new URL("oauth/silent-sso.html", location.href)`. When the page URL has no
  trailing slash (common after Keycloak redirect or EDA View navigation), the
  browser resolves this to `/core/httpproxy/v1/oauth/silent-sso.html` instead of
  `/core/httpproxy/v1/imagemanager/oauth/silent-sso.html`. Keycloak's check-sso
  iframe loads a 404, `init()` returns false, and bootstrap fails with *Sign in
  failed* even though the user is logged into EDA.
- **Fix:** Build silent-sso URI from `apiBase` (`location.origin + apiBase +
  "/oauth/silent-sso.html"`). Same for `loginRedirectUri` (registered proxy base).
- **Bootstrap:** Trust `im_session` via fast `GET /api/config` first; then
  keycloak-js check-sso; standalone tabs call `keycloak.login()` immediately on
  false (no sessionStorage guard on first bootstrap); embedded retries silent SSO
  only.
- **Bearer fallback:** Server accepts Keycloak bearer tokens on all `/api/*`
  routes (cable-map pattern); UI attaches bearer when cookie exchange fails.
- **UX:** Auth failure clears table *Loading…* placeholders with a sign-in message.

## v0.0.61

**Fix standalone View-link sign-in failure (v0.0.60 regression):**

- **Root cause:** Bootstrap called `GET /api/config` first, then spent up to ~16s on
  silent-SSO retries before attempting `keycloak.login()`. With an active EDA session,
  `check-sso` often returns false in a new tab; the delay let the 20s bootstrap timeout
  fire and showed *Sign in failed* before the cable-map auto-login redirect ran.
  `redirectUri` was rebuilt from `apiBase` instead of the full `location.href`, so
  post-login token exchange could fail after redirect.
- **Cable-map parity:** Run `keycloak.init` (`check-sso`) **before** API calls; on
  false in standalone tabs call `keycloak.login({ redirectUri: location.href })`
  **immediately** (no error banner, no SSO retries first). After redirect back,
  `processOAuthCallback` uses `login-required` + `POST /oauth/session`.
- **`redirectUri`:** Full current URL with OIDC noise stripped (preserves `?details=`).
- **403 exchange:** Shows role-denied message, not generic sign-in failure.
- **Embedded unchanged:** Trust `im_session` / silent SSO retries + **Try again** banner.

## v0.0.60

**Fix infinite "Signing in…" bootstrap hang (v0.0.59 regression):**

- **Root cause:** `stripOAuthQueryParams()` was missing a closing `}`, producing a
  JavaScript syntax error that prevented the entire auth IIFE from running —
  `ensureAuth()` never executed, `bootDone()` never called, KPIs stayed "—".
- **Bootstrap safety:** 20s cap on the full auth bootstrap; per-attempt SSO timeout
  reduced to 8s (2 retries). `ensureAuth()` always calls `bootDone()` in `finally`.
- **On timeout/failure:** embedded shows **Try again** banner; standalone auto
  `keycloak.login()` redirect or recoverable error — never hangs indefinitely.

## v0.0.59

**Fix standalone View-link sign-in failure (v0.0.57–58):**

- **Root cause:** `oauthCallbackFailed` blocked bootstrap on stale `?auth_error=callback`
  with a permanent *Sign-in could not be completed* banner; `im_auth_settled` was set
  before `keycloak.login()` finished, so a single silent-SSO or callback failure
  prevented all further auto-login attempts in the tab.
- **Cable-map parity:** Process keycloak-js OAuth callback before `GET /api/config`,
  retry silent SSO 3× with backoff, then at most one auto `keycloak.login()` in
  standalone tabs only (embedded never auto-login).
- **`redirectUri` fix:** Always uses registered proxy base
  `/core/httpproxy/v1/imagemanager/` (strips OAuth noise, preserves deep links).
- **No bootstrap failure banner** until silent SSO + optional auto-login are exhausted.

## v0.0.57

**Fix embedded View-link reload loop (v0.0.56 regression):**

- **Root cause:** v0.0.56 auto-called `keycloak.login()` inside the EDA embedded
  iframe when silent SSO failed. Cable-map uses the same fallback in a **new tab**,
  not an iframe — in embedded mode each `keycloak.login()` redirect reloaded the
  iframe (~1s cycle) with *Signing in…* on every pass. A premature `bootDone()`
  before `ensureAuth()` also hid then re-showed the signing-in state each reload.
- **Embedded:** Never auto `keycloak.login()` or server `/oauth/login` — silent SSO
  + token exchange only; show recoverable **Try again** banner on failure.
- **Standalone:** `keycloak.login()` at most once per session open via
  `im_auth_settled` guard; OAuth callback URLs use `onLoad: login-required`.
- **Boot shell:** *Signing in…* stays visible until auth completes (no early
  `bootDone()`).

## v0.0.56

**Fix auth redirect loop (v0.0.55 regression):**

- **Root cause:** v0.0.55 auto-fell back to server `/oauth/login` when silent SSO
  failed. If the OIDC code exchange failed, the app redirected to
  `/?auth_error=callback` and immediately retried `/oauth/login`, causing a
  ~1s full-page reload loop with *Signing in…* on every cycle.
- **Cable-map parity:** Auto-fallback now uses `keycloak.login({ redirectUri })`
  (public `auth` client) instead of the server confidential-client redirect.
- **Loop guard:** `sessionStorage` debounce + stop auto-redirect after
  `auth_error=callback`; show recoverable **Try again** / **Sign in** banner
  instead.
- **Embedded + standalone:** Same keycloak-js login fallback (cable-map shows
  *Signing in…* briefly, then opens — no reload loop).

## v0.0.55

**Fix View-link sign-in UX — match cable-map OIDC fallback (v0.0.54 gap):**

- **Root cause (v0.0.54):** When keycloak-js `check-sso` returned false (common even
  with a valid EDA GUI session), bootstrap called `requireSignIn()` and showed
  *Sign-in failed. Try again or use Sign in.* instead of falling through to OIDC.
  Cable-map calls `keycloak.login()` on the same path, which completes instantly
  when the user is already signed into EDA.
- **Cable-map parity:** Bootstrap shows **Signing in…** immediately; silent SSO
  retries once; standalone View links fall back to `/oauth/login` (OIDC redirect)
  before any error banner. Embedded iframe still shows **Try again** only.
- **Keycloak init:** `pkceMethod: S256` and same-origin `silentCheckSsoRedirectUri`
  via `new URL("oauth/silent-sso.html", location.href)` (cable-map pattern).
- **Deep links:** `?return=` on `/oauth/login` preserves `?details=` (and other
  query params) through the OIDC callback redirect.

## v0.0.54

**Fix sign-in failure — restore cable-map auth bootstrap (v0.0.39 pattern):**

- **Root cause:** v0.0.40+ auto-redirected to `/oauth/login` when silent SSO failed;
  a broken OIDC callback surfaced the plain-text error *Sign-in failed: could not
  complete authentication.* instead of a recoverable in-app state. `silentSso()`
  also created a throwaway Keycloak instance (cannot re-init reliably).
- **Cable-map parity restored:** trust `GET /api/config` 200 on bootstrap without
  Keycloak; deduped singleton `initKeycloakCheck()` with retry after iframe
  false-negatives; `loadConfigAfterExchange()` cookie-commit retries; all auth
  failures show **Try again** / **Sign in** banner (no auto redirect, no reload).
- **v0.0.52 retained:** embedded session probes trust server `im_session`; live
  indicator on all tabs; `checkLoginIframe` disabled in iframe.
- **OAuth callback:** code-exchange failure redirects back to the SPA with
  `?auth_error=callback` instead of a 502 plain-text page.

## v0.0.53

**Deep-linkable image details URLs:**

- Opening **Details** in the app now updates the browser URL with
  `?details=<uploadId>` (same query param the EDA dashboard View links already
  use). The URL stays copyable/shareable while the NodeProfile dialog is open.
- Loading `/core/httpproxy/v1/imagemanager/?details=<uploadId>` auto-opens that
  image's details dialog once artifact rows are loaded (unchanged behaviour, but
  the param is no longer stripped after open).
- Closing the details dialog clears the query param; browser **Back** / **Forward**
  opens and closes the dialog when navigating between detail URLs.

## v0.0.52

**Fix page refresh loop + live indicator on all tabs (cable-map pattern):**

- **No full-page reload:** Embedded session loss shows an in-app **Try again**
  banner (silent SSO re-exchange) instead of `window.top.location.reload()`.
  Standalone still redirects to `/oauth/login` on logout.
- **Embedded session probes:** Periodic and tab-focus checks trust
  `GET /api/config` 200 (server `im_session` cookie) — Keycloak
  `checkLoginIframe` is disabled in the embedded iframe to avoid false logout
  loops. Standalone probes still revalidate via Keycloak after bootstrap.
- **Live indicator:** Stays green on Upload, URL Import, and Settings tabs
  whenever auth is ready and background polling is active (not only on
  Dashboard). Pauses only while composing an upload or when the tab is hidden.
- **v0.0.49–v0.0.51 retained:** Upload form pause, deferred session loss,
  incremental artifact table DOM diff rendering.

## v0.0.50

**App bar wordmark + N favicon:**
The top bar shows the full **Nokia wordmark** (`nokia-logo.png`, 14px height);
the browser tab favicon keeps the **N mark** only (`nokia-n.png`).

## v0.0.49

**Background refresh no longer disrupts upload forms:**
Periodic polling and session checks could reload or re-render the UI while
the user was selecting a file or namespace on the Upload / URL Import tabs,
clearing the file input and form fields.

- **`refreshArtifacts()`:** Dashboard tab updates KPIs, storage ops cards, and
  the artifacts table; other tabs fetch data silently without touching form DOM.
- **`uploadFormActive()`:** Detects in-progress upload form state (file selected,
  namespace, name, license, URL import fields). Poll pauses entirely while set;
  session loss is deferred (same pattern as `uploadInFlight`).
- **Session probes:** `probeSession()` / `verifyKeycloakSession()` skip while
  the upload form is active; tab-focus revalidation debounce increased to 2s.
- **Live indicator:** Shows paused state while composing an upload.
- **`renderImports()`:** No longer triggers artifact table re-render off the
  Dashboard tab.

## v0.0.48

**Pre-upload duplicate check (replace dialog before transfer):**
Uploading or URL-importing an image whose name already exists (local PVC
`meta.json` or Artifact CR) now prompts **Replace it?** before any file bytes
are sent. Confirming retries with `replace=true`; cancel leaves no
`.incoming-*` temp dir on disk.

- **`GET /api/check-conflict`:** lightweight name + namespace existence probe
  (uses `uploads.to_k8s_name` + `import_common.check_conflict`).
- **`POST /api/upload`:** early 409 when `replace` is not set (before streaming
  the zip), in addition to the existing post-process guard.
- **UI:** progress row stays visible during replace uploads (pending row no
  longer hidden when a matching artifact row already exists; refresh no longer
  drops in-flight pending entries). HTTP 409 replace dialog kept as fallback.

## v0.0.47

**Storage reconcile: ignore empty in-flight temp dirs:**
Empty `.incoming-*` / `.import-*` shells (left behind when temp cleanup removed
files but not the directory) are no longer counted as in-flight work and are
removed immediately on reconcile instead of waiting for `STALE_WORK_DIR_SECONDS`.
The dashboard ops alert now uses the live work-dir count from `/api/artifacts`
(in addition to the periodic reconcile snapshot) so the banner clears as soon
as temp dirs are gone.

## v0.0.46

**Dashboard: OS column on Artifacts table:**
Each tracked upload now exposes `nosLabel` in `GET /api/artifacts` (mapped from
meta.json `nos`: `srl` → Nokia SR Linux, `sros` → Nokia SR OS, `srsim` →
Nokia SR OS (SIM)). The Status tab Artifacts table adds a sortable **OS**
column; the NodeProfile details title and delete confirm dialog show the label
when known.

## v0.0.45

**Fix EDA logout not signing out Image Manager (v0.0.43–v0.0.44 regression):**
Periodic session probes trusted `GET /api/config` alone, which stays 200 while
the `im_session` cookie is valid (up to 8h) even after EDA GUI logout.
`checkLoginIframe` / `onAuthLogout` could fire, but storage/tab revalidation
also called the same cookie-only probe.

- **`verifyKeycloakSession()` restored:** After bootstrap, probes and
  cross-tab `kc-*` storage events revalidate the singleton Keycloak client
  (`check-sso` + `updateToken`) instead of trusting the local cookie alone.
- **Immediate SSO loss on watch init:** If post-auth `initKeycloakWatch()` finds
  no Keycloak session, the UI runs the same path as **Sign out**
  (`POST /oauth/session/logout` + embedded top reload).
- **v0.0.44 bootstrap preserved:** Silent SSO still uses `checkLoginIframe:
  false`; upload-in-flight guard and deduped script load unchanged.

**Fix ghost artifacts after uninstall/reinstall:**
Managed Artifact CRs could survive app uninstall while the PVC was wiped (or
reinstall identity reset storage), and `_artifact_fallback_rows` listed them as
**Available** with empty size (eda-asvr still had the old copy).

- **Reinstall:** `reconcile_install_identity` now deletes all managed Artifact
  CRs when `ImageManagerConfig` UID changes (alongside PVC wipe).
- **Uninstall:** SIGTERM handler deletes managed Artifact CRs before removing
  the PVC when the Deployment has a `deletionTimestamp`.
- **Startup purge:** `reconcile_local_uploads` removes orphan managed CRs with
  no matching PVC `meta.json` (except in-flight downloads).
- **PVC-truthful status:** Dashboard rows use Image Manager PVC as the durable
  origin. **Available** / **Ready** only when local bytes exist *and* the
  Artifact CR reports Available. Missing PVC with an asvr-only copy shows
  **Asvr only**; missing files with meta present show **No local copy**; PVC
  present without CR shows **Needs republish** (existing repush_from_local).

**Replace on duplicate upload:**
HTTP 409 conflicts from upload and URL import open a confirm dialog; confirming
retries with `replace=true` (drops Artifact CRs only via `_ensure_replace`).

## v0.0.44

**Fix embedded bootstrap + EDA logout UX (v0.0.43 regression):**

- **Bootstrap gate:** The dashboard shell stays hidden until auth completes
  (`bootDone()` only after a successful `GET /api/config`). During silent SSO
  the UI shows **Signing in…** only — no Try again banner mid-bootstrap.
- **`authBootstrapComplete`:** `probeSession()`, `handleSessionLoss()`, and
  tab/storage revalidation are skipped until bootstrap finishes, preventing
  false session-loss banners while Keycloak SSO is still running.
- **Session probes:** On `401`, both embedded and standalone attempt one quiet
  silent SSO re-exchange before declaring session loss (restores v0.0.41 probe
  behaviour; v0.0.43 embedded early-`false` removed).
- **Embedded EDA logout:** Clears `im_session` then reloads the EDA shell
  (`window.top.location.reload()`) — no in-app Try again banner (cable-map
  pattern). Standalone tabs redirect to `/oauth/login` on logout.
- **Standalone bootstrap fallback:** When silent SSO truly fails, redirect to
  `/oauth/login` instead of the in-page **Sign in required** banner (empty KPIs
  + banner flash).
- **v0.0.43 retained:** Deduped Keycloak script load, upload-in-flight guard,
  post-auth `checkLoginIframe` + `onAuthLogout` watchers unchanged.

## v0.0.43

**Fix Keycloak script load breaking artifact refresh (v0.0.42 regression):**
v0.0.42 periodic probes called `verifyKeycloakSession()`, which re-fetched
`keycloak.min.js` every 15–30s. After EDA logout or identity-proxy
unavailability the script load failed and the error bubbled into
`refresh()` as “Failed to load artifacts: script load failed …” instead of
a clean sign-in banner.

- **Server-only session probes:** `probeSession()` uses `GET /api/config`
  again; embedded iframe never loads Keycloak during background checks (only
  on **Try again**). Standalone may attempt one quiet silent SSO on 401.
- **Deduped Keycloak script load:** `loadKeycloakScript()` shares one in-flight
  promise, skips reload when `Keycloak` is already defined, and stops retrying
  after a failed load until the user clicks **Try again** (`forceScript`).
- **Auth failures never break data refresh:** `handleAuthLoss()` always resolves
  to `handleSessionLoss()` (`POST /oauth/session/logout` + banner); 401 refresh
  retries only when `authReady` is restored.
- **v0.0.42 retained:** One-time post-auth `initKeycloakWatch()` with
  `checkLoginIframe` + `onAuthLogout`, Sign out button, storage/pageshow
  revalidation, v0.0.40 bootstrap, and upload-in-flight guard unchanged.

## v0.0.42

**Fix EDA logout not signing out the app (v0.0.41 regression):** v0.0.41 probes
only checked `GET /api/config`, which returns 200 while the `im_session` cookie
is still valid (up to 8h) even after EDA GUI logout. The separate post-auth
`logoutKc` watcher could also fail silently without clearing the UI.

- **Keycloak revalidation (cable-map pattern):** After bootstrap (`authReady`),
  a singleton Keycloak client runs with `checkLoginIframe: true` and
  `onAuthLogout` in the embedded iframe (not skipped). Periodic probes and
  tab-focus revalidation call `verifyKeycloakSession()` (`updateToken` +
  token re-exchange) instead of trusting the local cookie alone.
- **Cross-tab logout:** `storage` events on `kc-*` keys and `pageshow` after
  bfcache restore trigger immediate revalidation.
- **Sign out button restored:** Confirm dialog → `POST /oauth/session/logout`
  → `kc.logout({ redirectUri })` (fallback `/oauth/logout` server redirect).
- **v0.0.40 bootstrap preserved:** Silent SSO still uses `checkLoginIframe:
  false`; valid `im_session` on first load is trusted without pre-bootstrap
  Keycloak polling. v0.0.36 upload-in-flight guard unchanged.

## v0.0.41

**EDA logout sync (cable-map pattern, v0.0.40-safe):** After bootstrap completes
(`authReady`), detect EDA session loss without reintroducing v0.0.34–v0.0.39
bootstrap polling or shared Keycloak init. A lightweight `GET /api/config` probe
runs every 30s (plus tab-focus revalidation); when it returns 401, silent SSO
re-exchange is attempted once. A separate post-auth Keycloak watcher with
`checkLoginIframe: true` and `onAuthLogout` catches GUI logout while
`im_session` is still valid. On real session loss the UI calls
`POST /oauth/session/logout`, clears auth state, and shows a recoverable
sign-in banner (**Try again** / **Sign in** on standalone) — no full-page
redirect unless the user clicks **Sign in**. v0.0.40 bootstrap unchanged
(`checkLoginIframe: false` during silent SSO); v0.0.36 upload-in-flight guard
retained.

**PVC removed on uninstall:** Controller deletes `imagemanager-data` on SIGTERM
when the Deployment has a `deletionTimestamp` (app uninstall, not Recreate
upgrades). RBAC grants scoped delete/get on the claim plus get on the
Deployment. PVC label `eda.nokia.com/component: imagemanager-data` added. If
the claim still survives reinstall, startup compares ImageManagerConfig UID to a
PVC install marker and wipes stale upload bytes before reconcile/repush.

## v0.0.40

**Revert client auth to v0.0.30 silent SSO:** Restore the simpler pre-v0.0.33
auth flow that worked reliably in the EDA embedded iframe: trust a valid
`im_session` on load, run Keycloak silent SSO only when config returns 401,
`checkLoginIframe: false`, no periodic session polling, no Keycloak singleton
watchers, no in-page Try again / Sign in banner complexity, and no Sign out
button. Standalone tabs still fall back to `/oauth/login` redirect when silent
SSO fails. **Retained from v0.0.36:** upload-in-flight guard — auth redirects
and session-loss handling are deferred while a file upload is active, then
applied via `flushDeferredSessionLoss()` when the transfer completes.
`type="button"` on upload/action buttons unchanged. Server-side
`POST /oauth/session/logout` and token-bound session cookies (`te` field) kept.

## v0.0.39

**Durable embedded EDA sign-in (cable-map parity):** Simplify auth to two clear
paths. Bootstrap: `GET /api/config` → 200 trusts `im_session` with no Keycloak;
401 runs silent SSO once, exchanges the token, then retries config (with cookie
commit retries). Periodic checks probe the server only; Keycloak runs on 401.
All auth failures show a recoverable banner with **Try again** (embedded and
standalone) — never the fatal "Sign-in failed inside EDA" table-empty state.
Explicit `credentials: "same-origin"` on session fetches. v0.0.36 upload guard
and v0.0.37 no-refresh polling unchanged.

## v0.0.38

**Fix embedded EDA sign-in regression (v0.0.37):** Restore the v0.0.35 cable-map
bootstrap pattern after silent session-check changes reintroduced embedded SSO
failures. A valid `im_session` is still trusted on first load without Keycloak;
`probeSession()` and `handleAuthLoss()` are skipped until bootstrap completes;
Keycloak `init()` clears its dedupe promise on iframe false-negatives so silent
SSO can retry; embedded SSO errors show a recoverable banner instead of the fatal
"Sign-in failed inside EDA" message. v0.0.37 no-refresh polling and upload
in-flight deferral are unchanged.

## v0.0.37

**Silent session checks (no page refresh):** Periodic session polling, tab-focus
revalidation, and API 401 recovery no longer redirect to `/oauth/login` while the
user is still signed into EDA. Session probes use a lightweight `/api/config`
check with silent SSO re-exchange; standalone tabs also register Keycloak
`onAuthLogout` / `checkLoginIframe` watchers (cable-map pattern). On real session
loss the UI clears `im_session` via `POST /oauth/session/logout` and shows an
in-page sign-in banner with **Try again** (silent SSO) and **Sign in** (explicit
OIDC redirect only on button click). Upload in-flight deferral from v0.0.36 is
unchanged.

## v0.0.36

**Fix upload interrupted by page refresh:** v0.0.34/v0.0.35 session revalidation
(30s polling, tab-focus checks, Keycloak `verifyKeycloakSession`) could clear the
server session or redirect to `/oauth/login` while a file upload was still in
flight, aborting the transfer. Uploads now set an in-flight guard that defers
auth loss handling and skips SSO probes until the XHR completes; action buttons
use `type="button"` explicitly.

## v0.0.35

**Fix embedded EDA sign-in:** v0.0.33/v0.0.34 re-validated Keycloak SSO on every
load when an `im_session` cookie existed. Inside the EDA iframe, `checkLoginIframe`
and `check-sso` often false-negative, which cleared a valid cookie and left
`silentSso()` unable to recover (Keycloak `init()` cannot run twice). Image
Manager now trusts a valid server session on first load, dedupes Keycloak init,
disables the login-status iframe in embedded mode, and uses server-side session
probes plus silent SSO for periodic logout detection in the iframe.

## v0.0.34

**Auth hardening:** faster EDA logout detection and proper app sign-out.

- **Keycloak session iframe:** enable `checkLoginIframe` (login-status-iframe,
  ~5s) plus 30s backup polling — replaces the 2-minute-only interval.
- **Tab hygiene:** re-validate SSO immediately on tab focus, `storage` events
  (cross-tab EDA logout), and `pageshow` after bfcache restore.
- **Sign out:** app-bar **Sign out** with confirm dialog — clears the local
  `im_session` cookie, then `kc.logout({ redirectUri })` to end the EDA
  Keycloak session; server `/oauth/logout` falls back to RP-initiated logout.
- **Session cookies:** `Max-Age` is capped to the shorter of app TTL and access-
  token expiry; APIs still reject expired/invalid signed sessions (HttpOnly,
  Secure, SameSite=Lax unchanged).

## v0.0.33

App bar and favicon use the **Nokia “N” mark** only (`nokia-n.png`, cropped from
the wordmark). **Logout sync:** when the EDA Keycloak session ends, the UI
re-validates SSO on load and every two minutes, clears the local `im_session`
cookie via `POST /oauth/session/logout`, and shows the sign-in banner instead of
stale authenticated state. Server sessions now track access-token expiry.

## v0.0.32

Update app bar and favicon **Nokia wordmark** (`nokia-logo.png`) to the new
official blue logo asset (transparent background, cropped to the letters).

## v0.0.31

Replace app bar **Nokia wordmark** with a cleaner cropped asset (`nokia-logo.png`:
transparent background, tight crop around the blue letters).

## v0.0.30

Light mode app bar matches EDA shell (**`#f7f9fd`** background). Replace the custom
mark with the blue **Nokia wordmark** (`nokia-logo.png`, 14px height).

## v0.0.29

Light mode page background updated to **`#f7f9fd`** (EDA soft off-white).

## v0.0.28

App bar and browser tab use the new **logo.png** mark (30×30px in the header,
rounded corners); replaces the cable-map `eda.svg`.

## v0.0.27

Browser tab favicon uses the same **`eda.svg`** Nokia connect logo as the app bar
(cable-map / EDA pattern).

## v0.0.26

Remove **Sign out** from the app bar; EDA platform sign-out stays in the main GUI.

## v0.0.25

Replace the approximate Nokia wordmark with the same **`eda.svg`** connect logo
used by cable-map (served at `/assets/eda.svg`, displayed at 26px height).

## v0.0.24

Single top app bar (cable-map / EDA style) — removed the stacked two-tier header
and duplicate page hero. One row: **Nokia logo | Image Manager | Live | theme |
user | Sign out**.

## v0.0.23

Top header shows **Image Manager** next to the Nokia logo (replaces **Event Driven
Automation**). Sub-bar keeps the **Node Onboarding** nav category only.

## v0.0.22

EDA platform header parity for the standalone web UI (opened via **View** in a new tab):

- Two-tier chrome: **Nokia** wordmark + **Event Driven Automation** top bar, then
  **Node Onboarding → Image Manager** sub-bar with Live indicator.
- Theme toggle (moon/sun icon) switches light/dark; preference is persisted and
  defaults to the OS `prefers-color-scheme` on first visit.
- Embedded iframe view unchanged — EDA shell provides its own chrome.

## v0.0.21

Move EDA nav launcher from **Topology** to **Node Onboarding** (`ui.category: Node
Onboarding` on the dashboard view). Image uploads feed node bootstrap and image
upgrades, so the launcher belongs alongside onboarding resources.

## v0.0.20

Startup self-healing + pro ops UI + HA/storage guidance:

- **Storage reconcile on startup (node-agent parity):** the controller now
  re-derives upload state from the PVC and live Artifact CRs instead of trusting
  cached tracking. On every startup and every 10 reconcile cycles it: removes stale
  `.incoming-*` / `.import-*` temp dirs (configurable via
  `STALE_WORK_DIR_SECONDS`, default 1h); reports incomplete dirs (bytes but no
  `meta.json`); auto-repushes uploads whose PVC meta exists but Artifact CRs are
  missing (`repush_from_local`, no re-download).
- **Dashboard ops strip:** Controller / Storage / Reconcile cards show deployment
  mode, PVC posture, last reconcile, and surface warnings (in-flight work dirs,
  incomplete uploads, repush failures). Settings tab adds an HA & storage panel.
- **UI polish:** hero-style page header, improved status chips (`Needs republish`
  for `NoArtifact`), ops alert banner when reconcile finds issues.
- **Docs:** new `docs/resources/ha-and-storage.md` — PVC backup, external pull
  URL hook (`filePullBaseUrl`), why single-replica today, operational checklist.
- **`/api/artifacts`** now includes a `system` object (version, reconcile snapshot,
  work dirs). `/healthz` includes reconcile metadata.

## v0.0.19

Publisher redesign after live debugging against eda-sa — fixes stale rows for
good and makes every dashboard update land in under a second:

- **Root cause found (live-verified):** state DB launcher rows are EPHEMERAL —
  the aggregator purges all rows a publisher wrote the moment its gRPC stream
  ends. Whole-table deletes are rejected (`unknown oneof data_type` in eda-sa
  logs) but per-row predicate deletes work. And the daemon could wedge forever
  on a dead stream (no deadlines anywhere): a wedged daemon kept the deleted
  image's row frozen on the dashboard for hours — the "still shows Available"
  bug.
- **Daemon now owns the desired row set:** every payload is the full state;
  the daemon diffs against what it published on the current stream (per-row
  predicate deletes for removed images, adds for changes) and automatically
  REPLAYS everything whenever the stream is rebuilt (eda-sa restart, wedge
  recovery), because the server dropped it all.
- **No more wedges:** all sends run under a 10s watchdog that cancels the
  stream context, marks it broken and rebuilds on the next tick. Aggregator
  per-row errors are now logged instead of silently discarded.
- **Faster + simpler transport:** the controller writes payloads straight to
  the daemon's unix socket (no subprocess per publish); the client half-closes
  the socket so the daemon sees EOF immediately (a missing half-close was
  costing a silent multi-second stall per publish).
- **Dropped schema-registration RPCs:** tables auto-create on first add; the
  old create-style calls used a message shape the server can't parse and just
  spammed eda-sa error logs.
- Daemon restarts reset the sync snapshot so the full state is re-pushed
  (previously the change-detector could keep the dashboard empty forever
  after a daemon restart).

## v0.0.18

Event-driven dashboard sync (EDK/cable-map parity) — no more polling lag:

- **Kubernetes watch on Artifact CRs:** cable-map and other EDK catalog apps
  never poll — the runtime streams CR changes to them and they publish state
  DB rows on each change. Image Manager now does the stdlib equivalent: a
  long-lived cluster-wide watch on its managed Artifact CRs. The API server
  pushes ADDED/MODIFIED/DELETED the instant eda-asvr flips a download status
  or a CR appears/disappears (from the app UI, kubectl, anywhere), the
  tracked-list cache is dropped and the publish happens within ~0.5s.
- **Sync loop is event-driven:** it sleeps on a kick event (set by the watch
  and by UI upload/delete/replace actions) with a short safety-resync
  timeout, instead of blindly rebuilding every 2s. Bursts (multi-artifact
  uploads, watch reconnect replays) coalesce into one publish.
- Delete flow: UI delete already publishes inline; the watch now also fires
  on the CR deletion itself, so rows vanish from the dashboard immediately
  even when the CR lingered in Terminating at the moment of the inline
  publish, and even for deletions made outside the app. (Requires the
  v0.0.16 subtree-rebuild fix — targeted state DB row deletes are ignored by
  the aggregator.)

## v0.0.17

Dashboard shows the app within seconds of pod start (was minutes):

- **Status sync no longer waits for the reconcile settle delay:** the fast
  dashboard sync thread previously started only after `STARTUP_DELAY_SECONDS`
  (45s by default), so the first rows appeared a minute or more after pod
  start. It now starts immediately — it is cheap, no-ops when unchanged, and
  self-heals, so there is no reason to defer it.
- **Publisher daemon first-start failure now retried:** if eda-sa or the TLS
  mounts weren't ready at the moment the pod launched, the status-publisher
  daemon exited immediately and was never restarted (the watchdog only
  handled a daemon that had started and later died) — the dashboard stayed
  empty until the next pod restart. The sync loop now (re)starts the daemon
  whenever it isn't running.
- **Daemon stderr no longer piped into an undrained buffer** (could block the
  daemon after enough reconnect logging); it now goes to the pod log.

## v0.0.16

Deleted images now disappear from the dashboard immediately:

- **Stale row after delete fixed:** the aggregator does not honor targeted
  per-row deletes (`{.id=="..."}` predicates) sent over the StateDbUpdate
  stream, so a deleted image's row stayed on the dashboard even though the
  service row's image count dropped. Subtree deletes are reliable (the
  reinstall purge always worked), so every publish now rebuilds the whole
  `.cluster.apps.imagemanager.status` table: wipe the subtree, then re-add
  the current rows in the same ordered stream. The single `.app` row is
  simply overwritten in place.

## v0.0.15

Two distinct dashboard tables + version surfaced everywhere:

- **Dashboard split into two dashlets:** a compact **Image Manager Service**
  panel (Service | Health | HTTP | Version | Images | Status | View, backed by
  the new `.cluster.apps.imagemanager.app` state DB table) sits above a clean
  **Images** table (Image | Namespace | Status | View, backed by
  `.cluster.apps.imagemanager.status`). No more mixed summary + image rows in
  one table; image rows no longer carry empty app-level columns.
- **App version everywhere:** the controller version is published in the
  service dashlet (`version` column + info panel) and shown as a badge next to
  the app name in the web UI app bar (`/api/config` now returns `version`).
- **Publisher supports multiple tables:** rows carry an optional `path`
  selecting the target state DB table; the Go daemon registers schemas for
  both `.app` and `.status` and the startup purge wipes both, so reinstalls
  stay clean.

## v0.0.14

Seamless SSO from the dashboard + cable-map-style liveness columns:

- **No more Nokia EDA login page:** the fallback OIDC authorize URL now goes
  through the EDA **identity proxy** (`/core/proxy/v1/identity`) — the same
  Keycloak base the EDA GUI logs in through. Keycloak session cookies are
  scoped to that base path, so a logged-in user is 302'd straight back with a
  code (no login form). The previous URL used the Keycloak httpproxy path,
  whose cookie path never matched the GUI session, forcing a fresh login.
- **Dashboard shows app liveness (cable-map parity):** an always-present
  service summary row publishes `health` (Ready/Degraded) and `http`
  (Reachable/NoTLS/Down, self-reported by the serving thread) plus aggregate
  image counts — visible even with zero images, like cable-map's
  `data: Ready / http: Reachable` row. Columns are now
  Service | Health | HTTP | Image | Namespace | Status | View; per-image rows
  carry the image fields and leave the app-level cells blank.

## v0.0.13

Real-time dashboard sync fixes + row info panel:

- **Ghost "Available" after delete fixed:** deleted images no longer resurrect
  as fallback rows while their Artifact CR is still Terminating
  (`deletionTimestamp` now skipped).
- **Stale rows after reinstall fixed:** the first status sync of each process
  wipes the whole `.cluster.apps.imagemanager.status` table before re-adding
  current rows, so leftovers from a previous install (even with a deleted PVC)
  disappear as soon as the new controller starts.
- **Publisher self-healing:** the status-publisher daemon reconnects its gRPC
  stream when eda-sa restarts (recv-loop breakage detection + reconnect/replay
  on send failure), and the controller restarts the daemon if it dies.
  Status sync loop tightened to 2s (`STATUS_SYNC_INTERVAL`).
- **Row click shows YAML in the dashboard:** rows now publish a hidden
  `details` field carrying the NodeProfile YAML and the dashlet enables
  `showInfoPanel`, so clicking a row opens EDA's info panel (cable-map
  hidden-details pattern) instead of leaving the dashboard. The View link
  still deep-links into the app.
- **URL re-import responds immediately:** creating an ImageImport from the UI
  kicks the reconcile at once instead of waiting up to 60s, so a duplicate
  import surfaces its "already exists — Replace?" outcome within seconds.

## v0.0.12

Near-instant dashboard status + richer launcher columns:

- **Fast status sync:** dedicated 5s loop (`STATUS_SYNC_INTERVAL`) pushes
  `.cluster.apps.imagemanager.status` rows as soon as anything changes, instead
  of waiting for the 60s reconcile. Change-detection makes unchanged ticks
  free (no publisher spawn, no gRPC traffic). Upload/replace/delete in the app
  still sync immediately. Tracked-list cache TTL lowered 8s → 3s.
- **Dashboard columns fixed:** Service (constant "Image Manager"), Image
  (image/artifact name), Namespace, Status, View — matching the app's own
  status table.
- **Row deep links:** each row's `url` now points at
  `/core/httpproxy/v1/imagemanager/?details=<uploadId>`; clicking View on a row
  opens the app with that image's details dialog (NodeProfile YAML snippets)
  already open. The dialog gains a **Delete image** button, so an image can be
  inspected and deleted starting from the EDA dashboard (the EQL dashlet table
  itself is read-only, so deletion is confirmed in the app dialog).

## v0.0.11

UI redesign (cable-map pro look, dashboard-first):

- New layered-image brand logo (appbar + favicon).
- **Dashboard** is now the start tab: KPI overview cards (Images / Available /
  In progress / Failed), storage gauge, live artifact + URL-import tables,
  manual Refresh button.
- Adaptive reactive polling: 4s while uploads/downloads are in flight, 12s at
  rest, fully paused while the browser tab is hidden; Live pill reflects it.
- Seamless SSO from the dashboard View link: silent Keycloak `check-sso` runs
  first in **both** the EDA iframe and a new tab, reusing the existing EDA
  session with no redirect and no re-login; the OIDC redirect flow is only a
  fallback. Expired sessions self-heal on the next API call the same way.
- Authorization unchanged and enforced server-side: EDA OIDC + `ALLOWED_ROLES`
  (`imagemanager-viewer` EDA ClusterRole or `system-administrator`).

## v0.0.10

Fix empty Image Manager launcher table (cable-map app-status parity):

- **Root cause:** EQL on `imagemanagerconfigs` / `imagemanagerartifacts` returns no rows — CE logs
  `InvalidNamespaceOrGvk` for cluster-scoped imagemanager CRDs, and nested
  `ImageManagerConfig.status.artifacts` is not flat-table queryable.
- Controller publishes per-artifact launcher rows to `.cluster.apps.imagemanager.status`
  via bundled `status-publisher` daemon (persistent bidi `StateDbUpdate` +
  `StreamingJsonSchema` to `eda-sa.eda-system.svc:51100` with internal mTLS,
  reverse-engineered from cable-map EDK `dbStreamHandler`).
- Dashboard EQL switched to `.cluster.apps.imagemanager.status` with columns Name (`service`),
  Status (`status`), View (`open`) — matches cable-map dashlet field bindings.
- Deployment: mount internal EDA mTLS certs + trust bundle for state-aggregator access.
- `imagemanager-viewer` ClusterRole: `tableRules` for `.cluster.apps.imagemanager.**`.
- Remove 5-minute `LAUNCHER_SYNC_GRACE_SECONDS` skip (default `0`); `artifact_launcher` still
  syncs `ImageManagerArtifact` CRs every reconcile when uploads exist.

**Replace / overwrite:** When the user confirms Replace and the image already exists on the PVC,
the app now **republishes Artifact CRs from local storage** (eda-asvr re-pulls from the
controller) instead of re-downloading the URL or wiping the upload directory. Full delete
still removes PVC data via the Delete action.

**Known limitation (v0.0.10):** Launcher rows require the bundled `status-publisher`
daemon (persistent bidi `StateDbUpdate` + `StreamingJsonSchema` to `eda-sa`, cable-map
EDK parity). Cluster must run controller image `v0.0.10` with internal TLS volume
mounts from `app_deployment.yaml`.

## v0.0.9

Fix CE crash on install/upgrade and reduce API load during bootstrap:

- **CE panic fix:** add empty `ImageManagerArtifactSpec` to the
  `ImageManagerArtifact` CRD. CE's `propertiesBackwardCompatible` nil-dereferenced
  when the CRD had status only (no `spec` schema), crashing config-engine during
  v0.0.8 manifest publish and leaving the dashboard unregistered.
- Controller: 45s startup delay before first reconcile (`STARTUP_DELAY_SECONDS`).
- Controller: exponential backoff on reconcile errors (up to `MAX_RECONCILE_BACKOFF`).
- Launcher sync: skip `ImageManagerArtifact` CR writes for the first 5 minutes
  when there are no uploads yet (`LAUNCHER_SYNC_GRACE_SECONDS`).
- Node-agent DaemonSet: init container waits for controller `/healthz` before
  writing containerd registry redirects.
- Regenerate dashboard UUIDs; bump dashboard `version` to `0.0.9`.

## v0.0.8

Fix missing EDA left-nav entry (regression from v0.0.6):

- Revert manifest `ui.category` from **System** to **Topology** (cable-map and all
  working catalog apps use Topology; `System` is not registered for custom app views —
  same failure mode as the pre-v0.0.4 custom `Image Manager` category).
- Revert launcher EQL to `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerconfigs`
  (always has a `default` row; empty `imagemanagerartifacts` list can prevent view
  registration on fresh installs).
- Regenerate dashboard UUIDs and bump dashboard `version` to `0.0.8`.
- Keep `icon: CloudUpgrade` and cable-map structural clone (`flexRow` → `dashletDataView`).

## v0.0.7

Stability and API-load reduction (see `docs/STABILITY.md`):

- K8s client retries on HTTP 429/5xx (etcd init / overload).
- Reconcile interval 60s (env `RECONCILE_INTERVAL`); skip status PUT when unchanged.
- ImageImport URL downloads run in a background thread (uploads no longer block).
- Artifact list cache (8s) and Status tab poll interval 10s (was 5s).
- Node-agent: App Store setting `nodeAgentEnabled` (default true); `NODE_AGENT_ENABLED=false` skips `hosts.toml` writes; resync 120s; document scale-to-zero for non-SR-SIM labs.
- Uninstall: DaemonSet pods use `eda.nokia.com/app: eda-imagemanager` (same as Deployment) so EDA deletes both workloads; removed blocking `preStop` hook (SIGTERM cleanup only); shorter `terminationGracePeriodSeconds`.

## v0.0.6

Move EDA nav launcher from Topology to **System** category (`ui.category: System`,
`icon: CloudUpgrade`). Regenerate dashboard UUIDs so EDA re-registers the view after
the category change.

## v0.0.5

Rebuild EDA launcher dashboard from cable-map OCI reference (v0.2.2):

- Structural clone of `cable-map-dashboard.json` with fresh UUIDs (no reuse from cable-map or prior imagemanager).
- EQL on `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerartifacts` with columns Name, Size, Status, View.
- Manifest view icon changed from `Import` to `CloudUpgrade` (`ui.category: Topology`, view component last).

## v0.0.4

Fix missing EDA nav view (entire Image Manager panel absent):

- Restructure `imagemanager-dashboard.json` as a cable-map structural clone
  (`flexRow` → `dashletDataView`, external HttpProxy nav target) using simpler
  EQL on `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerconfigs`
  (always has a `default` row) instead of `imagemanagerartifacts` (empty list
  may fail view registration).
- Move manifest `view` component to last (cable-map pattern: workloads before view).
- Register nav under `ui.category: Topology` (cable-map uses Topology; custom
  `Image Manager` category never appeared in the nav tree).
- Match cable-map manifest view section field order (`category`, `icon`, `name`).
- Add `status.open: View` on ImageManagerConfig for launcher View column parity.
- Regenerate dashboard UUIDs and bump dashboard `version` to `0.0.4`.

## v0.0.3

Install/uninstall reliability aligned with cable-map patterns:

- Reorder manifest components: CRDs → RBAC → PVC → Service → Deployment → HttpProxy → DaemonSet (Deployment was previously applied before ServiceAccount/RBAC existed).
- Remove hardcoded `ghcr-imagemanager` imagePullSecret (EDA injects `appstore-eda-apps-registry-image-pull`; the missing secret caused install warnings and pull failures).
- Graceful controller shutdown: `preStop` sleep, `stop_file_server()` on SIGTERM, probes aligned with cable-map (`initialDelaySeconds`, no TCP startupProbe).
- DaemonSet `preStop` removes containerd registry redirect on uninstall so reinstall is not blocked by stale `hosts.toml`.
- Fix invalid `namespace` field on cluster-scoped `imagemanager-viewer` ClusterRole.
- Add `progressDeadlineSeconds: 600` and app labels on workloads/PVC/HttpProxy.

## v0.0.2

Fix EDA nav launcher dashboard after the v0.0.1 release reset:

- Restore cable-map-style dashboard JSON (`flexRow` → `dashletDataView`, external
  HttpProxy nav target) with flat EQL on `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerartifacts` (not broken `status.artifacts` nested paths).
- Regenerate dashboard UUIDs so EDA re-registers the view after the semver downgrade from v0.0.7 → v0.0.1 left a stale/missing nav entry.
- Confirm manifest bundles the `view` component and `imagemanager/ui` dependency; controller continues syncing `ImageManagerArtifact` launcher rows.

## v0.0.1

Initial public release (Image Manager for EDA):

- Web UI to upload SR Linux, SR OS hardware, and SR-SIM zips; automatic type detection, md5, and YANG schema profile resolution (schema-profiles or on-the-fly from `nokia/7x50_YangModels`).
- Controller file server, Artifact CR management, PVC-backed storage, and NodeProfile snippet helpers.
- EDA launcher dashboard with cluster-scoped `ImageManagerArtifact` CRs (flat status column bindings for EDA EQL).
- Offline air-gap bundle attached to each GitHub Release under `apps/imagemanager.eda.edacommunity.com/<version>`.
