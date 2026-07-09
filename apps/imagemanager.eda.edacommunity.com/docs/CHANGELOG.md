# Changelog

## v0.1.49

**UX refinement: professional EDA visual polish, tone down v0.1.48 chrome.**

- **Snackbars:** Reverted to subtle left-accent + lightly tinted background (not full green/red bleed).
- **KPI cards:** Clean number + label; tiny muted inline deltas; sparklines removed.
- **Artifacts table:** Search + namespace filters kept but restyled (single toolbar row, understated chips).
- **Row actions:** Restored Details / Delete icon buttons (revealed on row hover) instead of kebab menu.
- **Upload:** Minimal file picker — solid border, inline hint + file meta; drag-drop retained.
- **Dialogs:** Subtler motion (200ms, scale 0.98→1); focus trap unchanged.
- **Unchanged:** Self-contained controller (no npm build), themes, auth/SSO, `eda-embedded`.

## v0.1.48

**Visible UX polish: table filters, kebab actions, upload dropzone, KPI deltas, dialog motion.**

- **Artifacts table:** Search box (`#artifactFilter`) filters rows client-side; namespace
  filter chips row; per-row ⋮ kebab menu (Details, Copy snippet, Delete) replaces
  always-visible buttons; sortable column headers are keyboard-accessible buttons.
- **Upload tab:** Drag-and-drop `.dropzone` with hidden file input; selected file
  preview shows name, size, and detected OS badge; upload progress bar is taller
  with speed + ETA in prominent text.
- **KPI cards:** Visible `+N since last refresh` delta line under counts; sparklines
  on Total and Failed after a few polls.
- **Dialogs:** Scale+fade scrim/dialog transitions; Tab focus trap inside modals.
- **Snackbar:** Strong green/red full-tint backgrounds (clear ok vs err at a glance).
- **Unchanged:** Self-contained controller (no npm build), themes, auth/SSO,
  ripple, `eda-embedded`, concurrent uploads, URL import navigation.

## v0.1.47

**UX polish phase 1 — design tokens, icon sprite, KPI deltas.**

- **Design tokens:** Spacing scale (`--space-*`) and typography scale (`--text-*`,
  `--leading-*`, `--font-*`) in `:root`; major layout/chrome/KPI/chip/snackbar
  rules migrated to tokens; CSS grouped with section banner comments.
- **Icon sprite:** Hidden `<svg><symbol>` block; KPI, ops strip, theme toggle,
  empty states, and status chips use `<use href="#icon-*">` instead of scattered
  inline SVG paths.
- **KPI deltas:** Dashboard cards show `+N` / `-N` vs the previous poll when
  counts change.
- **Snackbar:** Stronger ok / err / info tint and 4px left accent bar.
- **Status chips:** Dot replaced with semantic status icons (ok, progress, warn,
  error, neutral).
- **Unchanged:** Self-contained controller (no npm build), themes, auth/SSO,
  ripple, dialogs, `eda-embedded`, concurrent uploads, URL import navigation.

## v0.1.46

**Remove cable-map references from docs and comments.**

- Docs, code comments, CRD/OpenAPI descriptions, and stability notes no longer
  cite cable-map; auth behavior unchanged (keycloak-js silent SSO, token
  exchange, embedded launcher).
- Deleted `docs/CABLE-MAP-UI-COMPARISON.md` and `docs/CABLE-MAP-ARCHITECTURE.md`.
- Rewrote `IMAGEMANAGER_PROJECT_SKILL.md` auth section for Image Manager only.

## v0.1.45

**Fix slow embedded EDA dashboard launch (iframe silent SSO).**

- **Root cause:** In the EDA dashboard iframe, `beginOAuthSignIn()` and the 8s
  `SIGNIN_SLOW_HINT_MS` timer showed an idle *Sign-in required* banner before and
  during silent SSO. Standalone tabs auto-`keycloak.login()` on 401; embedded
  stopped at the banner with no SSO until the user clicked. First iframe open also
  lacked `im_session` (direct URL often had it from a prior visit), so bootstrap
  hit the slow embedded branch every time.
- **Fix:** New `attemptEmbeddedSilentSignIn()` runs `check-sso` + `POST /oauth/session`
  immediately on 401 when `kc-*` localStorage signals an EDA session; keeps a
  *Signing in…* loading state (not the idle banner) until SSO fails. Parallel
  early SSO in `runConfigBootstrap()` when embedded + EDA session likely.
  `beginOAuthSignIn`, `showConfirmedSessionLoss`, and `applyConfig401` use the
  same fast path. Standalone 401 unchanged (silent SSO then `keycloak.login()`).
- **Unchanged:** v0.1.44 config-first fast path for valid `im_session`, logout
  reconcile, redirect URIs, bearer fallback.

## v0.1.44

**Fix version badge lag + faster sign-in (401 / silent SSO path).**

- **Version:** `main.py` `VERSION` was still `v0.1.42` while manifests were at
  `v0.1.43` — UI badge reads `/api/config` `c.version` from the running controller.
  All image tags, pyproject, dashboard JSON, and manifests bumped to **v0.1.44**.
- **Sign-in root cause:** v0.1.43 fast path skipped Keycloak only when `/api/config`
  returned 200. On 401 (no session), `handleBootstrap401` ran silent SSO + token
  exchange, then `finishConfigBootstrap` still called `backgroundValidateSession`
  (second `check-sso`, up to 8s + 20s). OAuth callback path had the same redundancy.
- **Fix:** Preload `keycloak.min.js` in `<head>`; shorter script/init/auth timeouts;
  `markFreshSignIn()` skips `backgroundValidateSession` after successful
  `POST /oauth/session` or OAuth callback prelude; 401 path uses a tighter silent-SSO
  budget; slow sign-in shows actionable banner after 8s instead of indefinite
  *Signing in…*.
- **Unchanged:** v0.1.43 config-first fast path for valid `im_session`, EDA catalog
  SSO, logout reconcile, redirect URIs, bearer fallback.

## v0.1.43

**Fast bootstrap when `im_session` is already valid (v0.1.42 slow load).**

- **Root cause:** v0.1.42 ran `bootstrapKeycloakPrelude()` (keycloak script + `check-sso` +
  token exchange) *before* `GET /api/config`, then blocked on `validateBootstrapSession()`
  (second `check-sso`) with a mandatory *Checking session…* banner before `onAuthReady`.
  Sequential 10s + 8s + 20s timeouts added up even on success — common dashboard
  open-with-session felt slow.
- **Fix:** `runConfigBootstrap()` fetches `/api/config` first (parallel keycloak script
  preload). On HTTP 200: `bootDone()` + `onAuthReady` + data loads immediately;
  `validateBootstrapSession()` runs in background (brief *Checking session…* only after
  600ms). Keycloak prelude limited to OAuth callback (`login-required`) only. 401 path
  unchanged (`handleBootstrap401` silent SSO). Keycloak init failure still non-fatal.
- **Unchanged:** keycloak-js SSO on no session, logout reconcile (v0.1.37+), redirect URIs,
  bearer fallback, embedded sign-in banner.

## v0.1.42

**Fix bootstrap brick when Keycloak prelude fails (v0.1.41 regression).**

- **Root cause:** v0.1.41 ran `keycloak.init(check-sso)` in the same promise chain as
  `GET /api/config` without a catch. Script load timeout, init timeout, or
  `redirect_uri` errors rejected the chain before `/api/config` ran, showing
  *Failed to load Image Manager configuration.* via `showFatal()` — the shell never
  reached `bootDone()` + sign-in banner or `onAuthReady`.
- **Fix:** New `bootstrapKeycloakPrelude()` attempts keycloak-js check-sso + token
  exchange first but catches all failures and continues to `/api/config`. OAuth /
  silent-SSO fallback (`handleBootstrap401`) still runs on 401. HTTP 5xx / network
  errors now show actionable messages instead of the generic fatal string.
- **Unchanged:** v0.1.41 redirect URIs, bearer fallback, `validateBootstrapSession`,
  concurrent uploads, URL import empty-state.

## v0.1.41

**Fix auth regression (v0.1.40).**

- **Silent SSO:** Restore `silentCheckSsoRedirectUri` =
  `apiBase + "/oauth/silent-check-sso.html"` (v0.1.40 wrongly used EDA `/`,
  breaking the check-sso iframe callback).
- **Redirect URIs:** `loginRedirectUri()` = app URL with OAuth params stripped
  (app URL with OAuth params stripped) for `keycloak.init` / `keycloak.login`.
- **Sign-in:** Interactive login uses `keycloak.login()` first; `/oauth/login`
  (confidential `eda` client) only as fallback.
- **Bootstrap:** Run `keycloak.init(check-sso)` before `GET /api/config`; standalone
  tabs auto `keycloak.login()` after silent SSO fails (embedded shows banner only).
- **checkLoginIframe:** Enabled in standalone tabs (`!embedded`), enabled in standalone tabs.
- **Bearer fallback:** `/api/*` accepts live Keycloak bearer tokens when `im_session`
  exchange lags (validates bearer on protected paths).
- **Unchanged:** v0.1.39 bootstrap timeouts, v0.1.37 logout reconcile, no IDP cookie
  gate on `verify_session`, concurrent uploads, URL import empty-state.

## v0.1.40

**Fix Keycloak `redirect_uri` mismatch (invalid parameter) on sign-in.**

- **Root cause:** v0.1.36 set `keycloak.init` / `keycloak.login` to imagemanager paths
  (`apiBase + "/"` and `apiBase + "/oauth/silent-check-sso.html"`). EDA's public
  `auth` client only registers the GUI root (`https://<host>/`), so check-sso and
  interactive login failed with *Invalid parameter: redirect_uri* — stuck on
  *Signing in…* then the Keycloak error page.
- **Fix:** `redirectUri` and `silentCheckSsoRedirectUri` now use
  `window.location.origin + "/"` (same as v0.1.35 `probeEdaOidcSilent`). Interactive
  **Sign in** / **Try again** use server `/oauth/login` (confidential `eda` client +
  imagemanager `/oauth/callback`) instead of `keycloak.login()` with an auth-client
  redirect that would strand users on the EDA home page.
- **Unchanged:** v0.1.39 bootstrap timeouts, v0.1.37 logout reconcile, v0.1.38 UMD
  keycloak, embedded no `window.top` hijack, `POST /oauth/session` token exchange.

## v0.1.39

**Fix infinite "Checking session…" bootstrap hang (v0.1.37 regression).**

- **Root cause:** v0.1.37 added `validateBootstrapSession()` with mandatory
  `keycloak.init({ onLoad: 'check-sso' })` before `onAuthReady`, but removed the
  v0.0.60 timeout guards. When silent check-sso never completes (iframe hang,
  CSP, or identity-proxy stall), the promise chain never resolves and the SPA
  stays on *Checking session…* forever — even though `bootDone()` already ran.
- **Fix:** Restore bounded waits — 10s script load, 8s `keycloak.init`, 20s full
  bootstrap/silent-SSO cap via `promiseWithTimeout`. Dedupe `loadKeycloakScript()`,
  verify `window.Keycloak` after load, log failures to console. On timeout or
  `authenticated === false`: fall through identity-probe fallback (v0.1.37) then
  `handleBootstrap401()` / embedded sign-in banner (never infinite spinner).
- **Unchanged:** Keycloak-js SSO when it works, v0.1.37 logout reconcile,
  v0.1.38 UMD keycloak build, embedded no `window.top` hijack.

## v0.1.38

**Fix startup crash: keycloak-js ES module loaded as classic script.**

- **Root cause:** v0.1.36 bundled the `keycloak-js` 26.2.4 **ES module** source
  (`export default class Keycloak`) as `/assets/keycloak.min.js`, but `loadKeycloakScript()`
  injects a plain `<script src>` tag expecting global `window.Keycloak`.
- **Fix:** Replace with a Rollup UMD build of `keycloak-js` 26.2.4 that exposes
  `window.Keycloak` for the self-contained SPA. Keycloak-js SSO flow unchanged
  (silent check-sso, `POST /oauth/session`, v0.1.37 logout reconcile).

## v0.1.37

**Fix EDA logout not disconnecting Image Manager (v0.1.36 regression).**

- **Root cause:** v0.1.36 trusted `/api/config` 200 + 8h `im_session` on bootstrap with
  no live Keycloak check, so a stale app cookie outlived EDA logout. Periodic
  `reconcileAuthState` relied on lenient identity probes (403 treated as OK) and
  did not use `keycloak-js` `check-sso` as the primary signal.
- **Bootstrap:** `validateBootstrapSession()` runs `keycloak-js` `check-sso` before
  `onAuthReady`. Stale `im_session` with no EDA session → clear cookie + sign-in.
  Inconclusive keycloak init falls back to identity probes (not probe-only, avoiding
  the v0.1.35 OAuth loop).
- **Reconcile:** `reconcileAuthState()` uses `ensureKeycloakSessionValid()` first;
  focus/pageshow trigger immediate reconcile; 3s interval unchanged (runs when tab hidden).
- **Server:** `POST /oauth/session` calls Keycloak userinfo after JWKS validation —
  rejects inactive sessions with 401.
- **Unchanged:** EDA catalog silent SSO pattern, no IDP cookie gate on `verify_session`,
  embedded sign-in banner, concurrent uploads, URL import empty-state.

## v0.1.36

**keycloak-js silent SSO + token exchange.**

- **Auth model (Option A):** Restore EDA SSO pattern — bundle `keycloak-js` 26.2.4
  as `/assets/keycloak.min.js`, serve same-origin `/oauth/silent-check-sso.html`
  (CSP `script-src 'self'`), and add `POST /oauth/session` to exchange a
  Keycloak public-client (`auth`) bearer token for the HTTP-only `im_session`
  cookie (JWT validated via JWKS; accepts `auth` or `eda` client `aud`/`azp`).
- **Bootstrap:** Shell loads without session; `GET /api/config` 401 runs silent
  `check-sso` + token exchange (no full-page `/oauth/login` redirect when EDA
  session exists). Existing `im_session` still trusted on 200 with no identity
  probe (v0.1.35 fix retained). OAuth callback (`?code=&state=`) processed before
  config fetch.
- **Sign in / Try again:** `keycloak.login()` with `/oauth/login` server OIDC
  fallback if the script fails.
- **EDA logout:** Dual identity probe + `kc-*` storage watchers unchanged;
  `verify_session` still has no IDP cookie gate.
- **Unchanged:** Embedded sign-in banner (no `window.top` hijack), concurrent
  uploads, URL import empty-state fix.

## v0.1.35

**Fix SSO login loop when opening Image Manager from the EDA dashboard.**

- **Root cause:** v0.1.32–v0.1.34 ran the dual identity probe (`login-status-iframe/init`
  + OIDC `prompt=none`) on **every bootstrap** after `/api/config` 200. The silent OIDC
  probe used `client_id=auth` with the imagemanager `/oauth/callback` redirect (valid
  only for `client_id=eda`), so it often returned `false` even for logged-in EDA users.
  `onIdentityProbeFailed()` then cleared the freshly minted `im_session` and restarted
  OAuth → infinite refresh loop.
- **Fix (kkayhan / EDA SSO pattern):** Bootstrap trusts server session only —
  `/api/config` 200 + user → `onAuthReady` with no identity probe. Identity probes
  run only in `reconcileAuthState()` when `authReady` (active session) to detect EDA
  logout. Silent OIDC probe now uses EDA `/` as `redirect_uri` for the public `auth`
  client; inconclusive probe results defer to the iframe probe instead of failing.
- **Unchanged:** Bootstrap 401 → `/oauth/login` silent SSO (v0.1.34); no IDP cookie
  gate on `verify_session`; embedded sign-in banner; `navigateTo` stays in-frame;
  concurrent uploads; URL import empty-state fix.

## v0.1.34

**Fix dashboard launch redirecting to EDA home instead of Image Manager.**

- **Root cause:** v0.1.32/v0.1.33 regressed bootstrap and session-loss redirects:
  `handleBootstrap401()` and bootstrap identity-probe failures called
  `redirectToEdaLogin()` (`/`) instead of `/oauth/login`; `navigateTo()` hijacked
  `window.top` in the EDA dashboard iframe, kicking users out of the shell.
- **Fix:** Missing `im_session` (401 on `/api/config`) and bootstrap probe failures
  before auth is established now start OAuth via `beginOAuthSignIn()` →
  `/oauth/login` (silent SSO when the EDA session is valid). Embedded mode shows
  an in-app sign-in banner with **Sign in** / **Try again** — never top-frame
  redirect. `navigateTo()` always stays in the current frame. Confirmed EDA logout
  during an active session still clears `im_session` and redirects standalone tabs
  to EDA `/`; embedded shows the banner only.
- **Unchanged:** Dual identity probe + 3s revalidation (v0.1.33); no IDP cookie
  gate on `verify_session`; URL import empty-state fix; concurrent uploads (v0.1.31).

## v0.1.33

**Fix EDA logout sync (dual identity probe) and URL import empty-state navigation.**

- **EDA logout (root cause):** v0.1.32's identity iframe `init` probe alone could
  still return OK after EDA sign-out — e.g. iframe `403` is ignored (v0.1.23 guard),
  or the body is not exactly `status:"changed"` while `im_session` keeps
  `/api/config` at 200. Background polling also paused when the tab was hidden.
- **EDA logout (fix):** Add a secondary OIDC `prompt=none` probe on the EDA identity
  proxy (`client_id=auth`); session is valid only when **both** probes agree. Treat
  any explicit iframe status other than `unchanged` as logout. Poll every 3s even
  when the tab is hidden; on tab focus run `reconcileAuthState()` immediately.
- **URL import empty state (root cause):** `data-goto` click handling was wired only
  on the artifacts `rows` table, not on `importRows`, so "Start a URL import" did
  nothing.
- **URL import empty state (fix):** Delegate `data-goto` clicks on `document.body`;
  switching to the URL Import tab focuses the source URL field.

## v0.1.32

**Auth: bootstrap identity probe, 3s revalidation, EDA login redirect.**

- **Root cause (stale logged-in UI):** v0.1.31 added the identity-proxy session probe in
  `reconcileAuthState()` but gated it on `authReady`, and bootstrap called `onAuthReady`
  immediately after `/api/config` 200 without probing. After EDA logout the 8h `im_session`
  cookie still returned 200, so refresh showed a logged-in shell until the first periodic
  check (8s later) — and session loss only showed an in-app banner instead of the EDA
  login page.
- **Bootstrap (EDA SSO pattern):** On every page load/refresh with a valid
  `im_session`, probe the EDA identity proxy (`login-status-iframe/init` via
  `client_id=auth` on `/core/proxy/v1/identity`) **before** `onAuthReady`. Invalid
  sessions clear `im_session` and redirect to the EDA login page (`/`).
- **Periodic revalidation:** Session poll interval shortened from 8s to **3s**; identity
  probe runs on every `reconcileAuthState()` when config is 200 (no `authReady` gate).
- **Session loss UX:** `showConfirmedSessionLoss` redirects to the EDA login page instead
  of leaving a stale logged-in UI with a recoverable banner.
- **Unchanged:** No identity-proxy cookies on `verify_session`; no Keycloak iframe from
  imagemanager origin; 403 probe responses ignored; concurrent upload fix from v0.1.31.

## v0.1.31

**Concurrent uploads for different images; EDA logout sync via identity probe.**

- **Concurrent uploads (root cause):** The Upload button and `setUploadBtnBusy()` used a
  global `uploadInFlight()` lock — any in-flight upload disabled the button and rejected
  new clicks, even for a different name+namespace pair. `doUpload` already deduped via
  `hasPendingFor` per image; only the button/global busy state was wrong.
- **Concurrent uploads (fix):** `syncUploadBtnState()` disables Upload only when the
  **current** form selection (name+namespace) has a pending row. Different images can
  upload in parallel; duplicate same-image uploads remain blocked. Replace flow and
  `sessionInterruptBlocked` upload guard unchanged.
- **EDA logout (root cause):** After EDA sign-out, Keycloak identity cookies are cleared
  but `im_session` remains valid (8h TTL) and `/api/config` keeps returning 200. EDA does
  not always clear `kc-*` localStorage keys, so storage watchers alone miss the logout.
- **EDA logout (fix):** After a successful `/api/config` probe, `reconcileAuthState()`
  also probes the EDA identity proxy Keycloak session iframe (`login-status-iframe/init`
  via `client_id=auth`). Only explicit `401` or JSON `status: "changed"` triggers
  `POST /oauth/session/logout` and the sign-in banner — **403 is ignored** (v0.1.23
  regression guard). Session poll interval shortened to 8s; `pageshow` always
  revalidates (not only bfcache). `kc-*` watchers retained.

## v0.1.30
**Fix sign-in: accept Keycloak JWT issuer formats behind the EDA proxy.**

## v0.1.29

**Republish Image Manager controller/UI with image tag `v0.1.29`.**

## v0.1.28

**Fix bootstrap stuck on "Loading Image Manager…" when unauthenticated.**

- **Root cause:** Bootstrap `GET /api/config` returned 401 and the SPA called
  `navigateTo(/oauth/login)` but never `bootDone()`, so the boot shell, KPIs
  (—), and table "Loading…" rows stayed forever when the redirect did not
  complete (embedded iframe or blocked navigation).
- **Fix:** New `handleBootstrap401()` always calls `bootDone()`, sets
  `authBootstrapComplete`, shows the sign-in banner with working **Sign in** /
  **Try again** buttons, and clears table loading placeholders. Standalone tabs
  still auto-redirect to `/oauth/login` after a short delay; embedded mode
  shows the banner only (EDA SSO pattern, no top-frame OAuth redirect).
- **Additional cause (this release hotfix):** `imagemanager/build/controller/webui.py`
  reassembled `INDEX_HTML` without preserving the opening `<script>` tag around
  the `_APP_JS` payload. The browser then rendered the JavaScript as visible
  page text (instead of executing it), so the app bootstrap never completed.
- **Additional fix:** preserve `<script>\n` when reassembling `INDEX_HTML`
  (keep the opening tag; inject only the JS payload contents).
- **Verified:** `im_session` cookie `Path` remains `APP_PROXY_PREFIX`;
  `auth.verify_session` trusts signed session TTL without IDP cookie gate
  (v0.1.25).

## v0.1.27

**Fix controller runtime JWT deps crash (PyJWT/cryptography).**

- Install PyJWT + cryptography in the controller runtime image so `import jwt`
  succeeds in Kubernetes (no `ModuleNotFoundError: No module named 'jwt'`).

## v0.1.26

**Harden JWT validation, improve maintainability, and expose operational metrics.**

- **JWT auth:** Verify Keycloak JWT signatures using JWKS (cached with TTL) and validate `exp`, `iss`, and `aud`/`azp`; added auth unit tests; ensure `_kc_admin_token` / `_client_secret` are never logged.
- **Trust boundary docs:** Add `SECURITY.md` documenting browser → identity proxy → app → Keycloak responsibility and session discipline.
- **Refactors:** Split `webui.py` `INDEX_HTML` into `_STYLE_CSS`, `_APP_JS`, and `_BODY_HTML`; decompose `uploads.py` into natural modules while keeping the original public API via re-exports.
- **Observability:** Add stdlib-only unauthenticated Prometheus `/metrics` endpoint for reconcile timing/failures, active uploads, storage usage, and node-agent heartbeat age.
- **CI guard:** Add `node --check` smoke test for the extracted JS block.

## v0.1.25

**Fix login infinite reload loop (critical regression from v0.1.24).**

- **Root cause:** `auth.verify_session` required identity-proxy Keycloak cookies
  (`KEYCLOAK_SESSION`, etc.) on every request. Those cookies are scoped to
  `/core/proxy/v1/identity` and are **not** sent to
  `/core/httpproxy/v1/imagemanager`, so a valid `im_session` was always rejected.
  Bootstrap `GET /api/config` returned 401 → redirect to `/oauth/login` → OAuth
  callback → reload → 401 loop; embedded mode also hit `window.top.location.reload()`
  in `retrySignIn`.
- **Fix:** Restore server trust in the signed `im_session` TTL. EDA logout sync
  remains client-side via `kc-*` localStorage watchers (v0.1.19+).
- **Unchanged:** `Cache-Control: no-store` on API responses and SPA `fetchJson`
  `cache: "no-store"` for GETs (v0.1.24 hardening retained).

## v0.1.24

**Fix EDA logout propagation on refresh (post-v0.1.23).**

- **Root cause:** The server accepted `im_session` based only on its own signed TTL;
  after EDA logout, `/api/config` could still return 200 for hours because session
  validity was not tied to live identity-proxy cookies anymore.
- **Fix:** `auth.verify_session` now requires identity-proxy Keycloak session cookies
  to be present on each request, and `fileserver._authed_user` passes the raw request
  cookie header so logout is reflected immediately on refresh.
- **Hardening:** API JSON responses now send `Cache-Control: no-store` and the SPA
  `fetchJson` helper forces `cache: "no-store"` for GETs, preventing stale auth state.

## v0.1.23

**Fix SSO login regression from v0.1.21 identity probe (critical).**

## v0.1.22

**Fix duplicate upload rows and false replace success during file upload.**

- **Duplicate rows:** Double-click Upload (or overlapping replace attempts) could create
  two `pendingUploads` entries for the same image — both showed identical Un-zipping
  progress. Guard the Upload button, dedupe pending by name|namespace, and hide server
  rows using `pendingMatchesServer` (including `uploadId`).
- **False replace / no upload:** `resetUploadForm()` ran before `xhr.send()`, which could
  invalidate the selected `File` in some browsers; the replace dialog now uses a captured
  `uploadFile` closure. `reconcilePendingUploads` no longer treats a **stale** PVC row
  (pre-upload `storedAt`) as completion during replace — that caused premature success
  snacks while the new zip was still transferring.
- **Unchanged:** URL-import replace still uses `repush_from_local` when the image is
  already on PVC (by design). File upload replace continues to stream the zip and
  `rmtree`+re-extract via `process_zip(replace=true)`.

## v0.1.21

**Fix EDA logout not clearing Image Manager session (v0.1.19 kc-* watcher insufficient).**

- **Root cause:** Image Manager trusts its own 8h `im_session` cookie via `/api/config`.
  EDA sign-out clears Keycloak **cookies**, not always `kc-*` localStorage keys, so the
  v0.1.19 storage watcher never fired and the app stayed “logged in” even after refresh.
- **Fix:** Probe the EDA identity proxy Keycloak session on bootstrap, every 15s while
  the tab is visible, and on `focus` / `pageshow` / `storage` revalidation. If
  `login-status-iframe.html/init` is not `unchanged` (403/401/`changed`) while
  `im_session` is still valid, immediately `POST /oauth/session/logout` and show the
  sign-in banner. `kc-*` watchers retained as a secondary signal.
- **Unchanged:** Upload `sessionInterruptBlocked` guard, OAuth flow, 2×401 probe trust model.

## v0.1.20

**Dashboard and form UI polish (self-contained webui).**

- **Information hierarchy:** KPI row spacing and a new “Inventory & imports” section divider separate overview cards from detail tables; the Failed KPI card gains a persistent err border and a `kpi-hot` highlight when failures are non-zero.
- **Tables:** Sticky headers, horizontal scroll at `min-width: 720px`, ellipsis + `title` tooltips on long names/namespaces/URLs; status chips use a unified semantic palette (`--ok-*` / `--warn-*` / `--err-*` / `--info-*`) with dot indicators and human-readable labels (“In progress”, “Needs republish”, etc.).
- **Empty & loading states:** Illustrated empty-state blocks for zero artifacts/imports (with Upload / URL Import actions) and structured error rows instead of bare `<tbody>` text.
- **Tabs & badges:** `focus-visible` rings on tabs and sortable headers; Dashboard active-work count badge uses alert styling when in-flight work exists.
- **Forms:** URL Import helper text; primary import button shows `aria-busy` spinner while the request is in flight.
- **Notifications:** Snackbar and auth-banner loading states align with the same semantic color tokens as KPI cards and status chips.
- **Responsive & a11y:** KPI grid wraps at 900px / 480px; `prefers-reduced-motion` respected; light-theme shadow overrides retained.
- **Unchanged:** OAuth/session-watcher JS, upload/polling logic, and CSS variable names used by JS (`imagemanager-theme`, etc.).

## v0.1.19

**Fix standalone-tab logout sync when EDA signs out (v0.1.18 regression).**

- **Root cause:** v0.1.18 gated Keycloak `kc-*` localStorage watchers behind
  `embedded` only, assuming standalone new-tab mode would rely on `/api/config`
  polling. After external-launcher became the primary mode, logging out of EDA
  cleared `kc-*` on the shared origin but Image Manager kept a valid `im_session`
  cookie (up to 8h) and never noticed until a 60s probe — if at all.
- **Fix:** Restore v0.1.17 targeted `kc-*` watchers for **all** modes (standalone
  and embedded). Same-origin tabs share `localStorage`; debounced `storage` events
  on `kc-*` keys plus sustained absence (~1.2s) after a prior sighting immediately
  POST `/oauth/session/logout` and show the sign-in banner without waiting for
  `/api/config` 401.
- **Unchanged:** v0.1.15 `/api/config` trust model (2× 401 over ≥5s for probe-only
  loss), 60s background poll, upload `sessionInterruptBlocked` guard, dashboard
  external-launcher JSON from v0.1.18.

## v0.1.18

**EDA nav: external-launcher pattern (no iframe embed).**

- **Dashboard JSON:** full EDA dashboard with `flexRow` + `dashletDataView` launcher
  cards; `navigationTarget.edaRoute = "external"` opens
  `/core/httpproxy/v1/imagemanager/` in a new tab (`useNewTab: true`). Removed
  top-level `type: iframe` / `url` / `sameOrigin`. Fresh dashboard UUIDs;
  EQL on `.cluster.apps.imagemanager.app` (service row) and
  `.cluster.apps.imagemanager.status` (per-image rows).
- **Session watchers:** standalone tab is the normal case after external launch;
  `/api/config` every 60s remains the primary logout detector (v0.1.15 trust
  model unchanged). Keycloak `kc-*` storage watchers are retained for iframe edge
  cases only — gated behind `embedded`, no longer load-bearing in new-tab mode.
- **Access:** `imagemanager-viewer` ClusterRole already grants `urlRules` for
  `/core/httpproxy/v1/imagemanager/**` and `tableRules` for
  `.cluster.apps.imagemanager.**`; view component remains last under
  **Node Onboarding**.

## v0.1.17

**Embedded EDA logout sync — detect parent sign-out without full page refresh.**

- **Root cause:** v0.1.15 removed Keycloak `kc-*` storage watchers to stop false
  sign-in banners; embedded Image Manager no longer noticed when the EDA parent
  logged out (`im_session` can remain valid server-side for up to 8h).
- **Targeted watchers (embedded + shared-browser tabs):** debounced `storage`
  events on `kc-*` keys (and `localStorage.clear`); sustained absence (~1.2s)
  after a prior `kc-*` sighting clears `im_session` and shows the sign-in banner
  without waiting for `/api/config` 401.
- **Safe probes:** periodic and visibility-triggered checks still use
  `/api/config` only (2× 401 over ≥5s); no `keycloakStoragePresent` veto on 200,
  no focus/pageshow churn, upload guard unchanged.
- **Embedded poll:** `/api/config` every 25s when tab visible (60s standalone).

## v0.1.16

**Fix late upload-done snack — timely feedback when bytes land, not only at Available.**

- **Root cause:** v0.1.14 kept pending upload rows through the post-upload `NoArtifact`
  grace window until `Available`/`Ready`, deferring the success snack to
  `reconcilePendingUploads`. Proxy/XHR drops during server finalize also routed to
  `holdUploadForReconcile`, which showed a sticky error snack and waited for full
  reconcile before any positive acknowledgment.
- **Early feedback:** snack "Upload received — processing …" when XHR body transfer
  completes (`onBodySent`), before server unzip/finalize returns.
- **POST success:** existing "Uploaded …" snack still fires on `200` from
  `/api/upload` (unchanged).
- **Reconcile:** clear pending as soon as a matching server row exists; show
  processing snack if none shown yet; shorter "X is Available." when early snack
  already fired. `effectiveDownloadStatus` still maps grace-period `NoArtifact` to
  `InProgress` so the republish flash fix from v0.1.14 is preserved.
- **Finalize drops:** `holdUploadForReconcile` now shows a non-sticky ok snack
  instead of a scary error when the connection ends during server processing.
- **Faster poll:** 2s artifact refresh for 2 minutes after upload starts (burst
  window), then existing 4s/12s adaptive intervals.

## v0.1.15

**Definitive fix for false sign-in banner while EDA session stays active.**

- **Root cause (client):** `probeSession()` treated missing `kc-*` localStorage keys
  as session loss even when `GET /api/config` returned `200`. Keycloak iframe churn
  fired `storage` / `visibilitychange` / `focus` revalidation, which repeatedly
  triggered the banner while the user remained signed into EDA.
- **Root cause (server):** `verify_session()` invalidated `im_session` when the OIDC
  access-token `te` field expired (~minutes) even though the app session `exp` was
  still valid for 8 hours — `/api/config` could return `401` with an active EDA GUI
  session.
- **Trust model:** Only `GET /api/config` decides auth. `200` always dismisses the
  banner; `401` must occur on 2+ probes at least 5s apart with no `200` in between
  before showing sign-in-required UX. Network/non-401 errors never show the banner.
- **Removed false-positive sources:** Keycloak `kc-*` storage watcher, focus/pageshow
  session revalidation, dual-endpoint `/api/settings` confirmation, deferred session
  loss queue, upload-session-loss UI during transfers, and `keycloakStoragePresent()`
  veto.
- **Background poll:** `/api/config` every 60s (was 30s); upload keepalive only recovers
  on `200`, never triggers loss UI.

## v0.1.14

**Fix false "Needs republish" flash after upload.**

- **Root cause:** After upload finalize, PVC bytes exist before Artifact CR
  `downloadStatus` is populated. `_resolve_download_status` returned
  `NoArtifact` (UI chip: **Needs republish**) even inside the post-upload grace
  window that already treated transient `Error`/`Failed` as `InProgress`.
  `_aggregate_download_status` also ranked `NoArtifact` above `InProgress`, so
  multi-part uploads could flash republish while one CR was still settling.
  `reconcilePendingUploads` cleared the pending row as soon as any server row
  appeared, exposing that transient status.
- **Server grace:** During `UPLOAD_FAILURE_GRACE_SECONDS`, missing/empty CR
  status with local bytes now reports `InProgress` instead of `NoArtifact`.
- **Aggregation:** `InProgress` wins over `NoArtifact` when parts converge at
  different speeds.
- **UI smoothing:** Client maps recent `NoArtifact` rows to `InProgress` for
  display/KPIs; pending upload rows stay visible until the server leaves the
  transient republish state or reaches `Available`/`Ready`.

## v0.1.13

**Fix stuck Un-zipping row and false sign-in banner after upload.**

- **Root cause:** `reconcilePendingUploads()` only cleared pending rows marked
  `awaitingReconcile`, so a hung XHR in the `Unzipping` phase could hide the
  server `Available` row indefinitely. A false `uploadSessionLost` flag also
  disabled the upload auth guard (`sessionInterruptBlocked`), allowing the
  sign-in banner while the pending row remained; polling then stopped because
  `authReady` was false.
- **Server-truth reconcile:** any pending upload whose name/namespace matches an
  artifacts row is cleared immediately — the server row wins (especially
  `Available`/`Ready`).
- **Upload auth guard:** session interrupts stay suppressed for the full pending
  upload lifetime; suspected expiry during upload is deferred quietly.
- **Polling during upload:** status refresh continues while pending uploads
  exist even if auth UX was briefly tripped.
- **Session-loss gate:** `handleSessionLoss()` re-probes `/api/config` before
  showing the sign-in banner; successful artifacts refresh always restores
  `authReady` and dismisses stale banners.

## v0.1.12

**Fix false sign-in banner when upload reaches Available.**

- **Root cause:** `probeSession()` treated `confirmAuthExpiryFrom401()`'s
  *expired* boolean as *session-ok*, so a transient `401` during post-upload
  re-probe called `handleSessionLoss()` even when dual-endpoint confirmation
  said the session was still valid. Deferred loss from mid-upload was also
  never cleared when pending upload reconciled to `Available`/`Ready` because
  `flushDeferredSessionLoss()` ran while `pendingUploads` was still non-empty.
- **Probe semantics:** `401` responses now map to session-ok only when expiry
  is *not* confirmed (`!expired`).
- **Reconcile success:** clearing a pending upload to `Available`/`Ready` resets
  auth-loss streaks, clears deferred session loss, dismisses any auth banner,
  and starts a short post-upload grace window before hard session-loss UX.
- **Recovery paths:** `/api/config` `200` after upload (keepalive, flush, or
  artifacts refresh during grace) clears deferred loss and restores
  `authReady`/live indicator without showing the sign-in banner.

## v0.1.11

**UI polish and smoother auth/session UX.**

- **Design refresh:** Refined app bar (backdrop blur, taller chrome), live indicator glow pulse, KPI/ops card hover depth, cleaner tab transitions, accent snackbar toasts, and upload progress bars with smoother width transitions.
- **Auth banner component:** Consolidated sign-in, signing-in, signing-out, and error states into one animated banner with spinner, title, and action buttons.
- **Session transitions:** Authenticated bootstrap fades out the loading shell and reveals the user chip without flash; sign-out shows a brief "Signing out…" state; auth banner dismisses with a smooth collapse animation.
- **Reactive status:** Status chips pulse briefly when a row's status changes during live polling.

## v0.1.10

**Fix recurring false auth interruptions during upload/reconcile.**

- **Root cause:** a single transient `401` from polling/status endpoints could still trigger the auth-loss path while upload finalization/reconcile was in progress, even when the EDA session remained valid and the Artifact soon became `Available`.
- **Confirmed-expiry gate:** UI auth-loss handling now requires a multi-hit `401` streak plus dual endpoint confirmation (`/api/config` and `/api/settings`) before showing sign-in-required state.
- **Upload/reconcile separation:** active upload and pending-reconcile states now suppress hard auth transitions unless expiry is confirmed; successful probes reset auth-loss suspicion automatically.
- **Status UX consistency:** when a pending upload resolves to `Available/Ready`, auth-loss suspicion is cleared so users do not see contradictory expiry behavior after a successful finalize.

## v0.1.9

**Fix artifact API hard-fail regression during status aggregation.**

- **Root cause:** `/api/artifacts` could fail the full request when one malformed/legacy `meta.json` row triggered an exception while building tracked rows, which surfaced as HttpProxy `HTTP 502` in the UI.
- **Cleaner behavior (kkayhan-style):** the artifacts endpoint now degrades gracefully; bad rows are skipped with warning logs, and response payload fields fall back to safe defaults instead of returning a 5xx.
- **Upload/status continuity:** status polling and pending-upload reconciliation keep running even if one stored row is invalid.

## v0.1.8

**Fix upload session-expiry false positives with verified auth-loss probes.**

- **Root cause:** v0.1.7 marked upload session loss on a single `401` signal during long transfers (`/api/config` keepalive tick or upload final response), which could coincide with transient proxy/network blips while backend reconcile still completed successfully.
- **Verified expiry only:** Upload flow now requires consecutive explicit `/api/config` `401` responses plus a confirm probe before showing the "Session expired during upload" banner.
- **Reconcile-first behavior:** While uploads are in `Unzipping`/`Processing`, transient request drops stay in reconciliation mode first; hard expiry is deferred unless auth-loss probe confirmation succeeds.
- **Recovery UX preserved:** True session expiry still shows the sign-in recovery message; valid sessions continue through automatic status reconciliation without manual sign-in.

## v0.1.7

**Fix deep-link handling and transient upload failure state.**

- Dashboard deep links now use the stable HttpProxy app path and open details by `uploadId` or image name.
- Opening Details in the UI now updates the `?details=` query param; closing the dialog clears it.
- New uploads treat early backend `Error/Failed` signals as `InProgress` for a short grace period, preventing false failure flashes while reconcile converges.
- If a long upload request drops after transfer (`Unzipping`/`Processing`), the UI keeps tracking backend completion automatically instead of showing a false terminal failure.
- Upload keepalive checks now detect true session expiry during long transfers and immediately show a sign-in recovery path.

## v0.1.6

**Fix false session loss during active uploads.**

- **Root cause:** v0.1.4 session watchers plus 4s status polling called
  `handleAuthLoss()` on transient `/api/artifacts` 401s while an upload XHR
  was in flight, showing "Session ended. Finish your upload, then reload." and
  hammering the API in a retry loop even though the EDA session was still valid.
- **Upload guard:** While `pendingUploads` is non-empty, session probes always
  trust the server cookie, API 401s are deferred silently (no snack, no
  `clearServerSession`), and polling does not re-enter auth recovery.
- **After upload:** `flushDeferredSessionLoss()` re-probes before showing the
  sign-in banner so false alarms from mid-upload noise are dropped.

## v0.1.5

**Hide in-flight upload work-dir operator alert.**

- **Reconcile ops strip:** No longer surfaces "in-flight upload/import dir(s) on disk"
  during normal uploads — that count is expected scratch state on the PVC, not an
  operator issue.
- **Attention count:** Reconcile card "attention" now reflects only incomplete upload
  dirs and automatic republish failures.

## v0.1.4

**Fix live indicator, upload status polling, and EDA session sync.**

- **Live indicator:** Header pill now reflects auth + controller health + tab
  visibility only — no longer greyed on non-Dashboard tabs or while composing an
  upload. Polling continues in the background during uploads.
- **Upload status:** Pending rows clear immediately when the upload XHR
  completes; background polling no longer pauses during in-flight uploads, so
  Dashboard status updates without a manual refresh.
- **EDA logout sync:** Restore session watchers — periodic `probeSession()`,
  `kc-*` storage events, focus/visibility handlers, and
  `POST /oauth/session/logout` to clear `im_session` when the parent EDA
  Keycloak session ends. Shows a recoverable sign-in banner instead of leaving
  a stale logged-in iframe.

## v0.1.3

**Fix artifact TLS pulls after internal-CA rotation.**

- `ensure_trust_bundle` now updates the per-namespace `imagemanager-trust-bundle`
  ConfigMap when the cert-manager CSI serving CA changes, not only on first create.
- Storage reconcile refreshes trust bundles for every namespace with uploads or
  managed Artifacts so `eda-asvr` always trusts the current serving certificate.

## v0.1.2

**Fix sign-out and EDA SSO session persistence.**

- Sign out clears `im_session` and redirects through Keycloak RP-initiated
  logout to the EDA login page (`/` on the cluster host), not a dead-end HTML
  page or `/oauth/login` loop.
- Restore ungated UI shell (`GET /`) so the SPA bootstraps via `GET /api/config`
  and redirects to `/oauth/login` only when needed — embedded EDA SSO works
  when the user already has an EDA Keycloak session.
- Sign-out and auth-loss navigation use `window.top` in the EDA iframe.
- Session cookies are again bound to Keycloak access-token expiry.

## v0.1.1

**Restore server-side OIDC auth (drop keycloak-js).**

- Replace broken client-side keycloak-js silent SSO with proven
  server-side Authorization Code flow: unauthenticated requests redirect to
  Keycloak via `/core/proxy/v1/identity`; callback exchanges code in-cluster
  (trusting `eda-api-ca` for TLS).
- Remove vendored `keycloak.min.js`, `/oauth/session`, silent-sso.html, and
  keycloak-js bootstrap from the UI. Sign out clears the local `im_session`
  only (EDA Keycloak session stays).
- UI and upload features unchanged; auth diff only.

## v0.1.0

**Fresh start — stability baseline.**

- Reset semver to **v0.1.0** after clearing all prior releases, catalog tags, and
  GHCR packages (clean slate).
- **Bundled keycloak-js** (`/assets/keycloak.min.js`): the EDA identity proxy no
  longer serves `keycloak.min.js` (HTTP 404); bundling matches EDA catalog and
  keeps silent SSO working.
- **Stability baseline:** retain the v0.0.51-era auth bootstrap (keycloak-js
  silent SSO + explicit Sign in / Try again) without the v0.0.52–v0.0.72 auth
  experiment churn; adopt proven discipline — fewer moving parts, one
  version bump per intentional release.

## v0.0.72

**Fix sign-in: vendor keycloak-js (identity proxy no longer serves it).**

- **Root cause:** `loadKeycloakScript()` fetched
  `/core/proxy/v1/identity/js/keycloak.min.js`, which returns HTTP 404 on this
  cluster (`Unable to find matching target resource method`). Silent SSO and
  Sign in never started — bootstrap failed with *Sign-in failed* / *could not
  complete authentication*. EDA catalog apps work because it bundles keycloak-js in its
  SPA bundle, not from the identity proxy.
- **Fix:** Ship `keycloak-js` 26.2.4 as `/assets/keycloak.min.js` from the
  controller; UI loads it from `apiBase + "/assets/keycloak.min.js"`.

## v0.0.71

**Fix sign-in: stop using broken server `/oauth/login` flow.**

The error *Sign-in failed: could not complete authentication* comes from the
server confidential-client code exchange (`exchange_code`) failing — not the
node agent. v0.0.70 still routed Sign in through `/oauth/login`, which hits
that broken path.

- **Sign in / Try again:** keycloak-js public client `auth` + `POST /oauth/session`
  (EDA SSO pattern) — never `/oauth/login`.
- **Bootstrap:** silent SSO only; on failure show banner (no auto-redirect).
- **Session:** trust `im_session` cookie in probes; no Keycloak iframe logout veto.
- **Tab persistence** and in-place session-loss banner (no navigation on background checks).
- Server callback exchange failures redirect to SPA instead of plain-text 502.

## v0.0.70

**Full rollback to v0.0.51 controller code** (`037f8cb`): reverts all auth
experiments from v0.0.52 through v0.0.69 (OIDC fallbacks, signed state,
keycloak.login loops, no-dashboard-reset patch, etc.). Ships as a new image tag
so clusters can upgrade off the broken releases.

## v0.0.69

**Permanent auth fix — trust controller session cookie, reliable Sign in:**

- **Root cause:** `startSessionWatchers()` ran Keycloak `check-sso` after every
  successful login; false-negatives immediately called `handleSessionLoss()` and
  cleared a valid `im_session` — sign-in appeared to work then instantly failed.
- **Session lifecycle:** watchers now use cookie-only `probeSession()` (no Keycloak
  iframe veto). `onAuthLogout` and cross-tab storage events confirm via probe first.
- **Sign in:** uses server `/oauth/login` (confidential `eda` client + signed
  state from v0.0.67) — the reliable path; keycloak-js is silent-SSO / Try again only.
- **Cookie race:** `loadConfigWithRetry()` after OAuth callback / token exchange.

## v0.0.68

**Fix auth redirect loop (v0.0.67 regression):**

- Bootstrap no longer auto-calls `keycloak.login()` or `/oauth/login` on silent
  SSO failure — stops the full-page reload loop showing *Loading Image Manager*.
- Failed bootstrap shows the in-place **Try again** / **Sign in** banner and always
  calls `bootDone()` so the shell is visible.
- **Sign in** / **Try again** are user-initiated only; server OAuth + signed state
  (v0.0.67) remain as explicit fallbacks.

## v0.0.67

**Fix OAuth "invalid state" and sign-in failures:**

- **Signed OIDC state** (`auth.py`): CSRF state is HMAC-signed in the URL so
  `/oauth/callback` no longer depends on the `im_oauth_state` cookie surviving
  the Keycloak redirect hop (common proxy/cookie loss cause of *invalid state*).
- **Callback errors redirect to SPA** (`/?auth_retry=1`) instead of a plain-text
  error page; bootstrap retries silent SSO.
- **Sign in uses keycloak-js first** (keycloak `login()` to SPA root), with
  server `/oauth/login` only as last resort.
- **Return-from-login**: `processKcCallbackReturn()` handles `?code=&state=` on
  the SPA URL after keycloak-js redirect.

## v0.0.66

**v0.0.51 UX patch (no-dashboard-reset):**

- **Tab survives reloads:** `showTab()` persists the active tab in `sessionStorage`;
  after a successful auth bootstrap the saved tab is restored instead of defaulting
  to Dashboard.
- **Background checks no longer navigate:** `handleSessionLoss()` only shows the
  in-place sign-in banner — no `window.top.location.reload()` or redirect to
  `/oauth/login`. Navigation happens only when the user clicks **Sign in**.
- **Trust server session cookie:** `probeSession()` treats `GET /api/config` 200 as
  sufficient; Keycloak/silent-SSO runs only on a genuine 401.

## v0.0.65

**Full restore to v0.0.51 codebase:** Check out the entire
`imagemanager/build/controller/` tree and manifest image refs from commit
`037f8cb` (v0.0.51 — last working sign-in). Replaces the partial v0.0.64 revert
that left version/manifest drift and did not fully reset deployable artifacts.

## v0.0.64

**Revert auth to v0.0.51 baseline (working sign-in):** Restore `webui.py`,
`fileserver.py`, and `auth.py` from v0.0.51 (`037f8cb`) — the last release with
reliable sign-in before v0.0.52–v0.0.63 auth regressions. Drops v0.0.52 session
refresh changes, v0.0.53 deep-link URL sync, and v0.0.55–v0.0.63 OIDC
fallback experiments. **Retained from v0.0.51:** incremental artifact table DOM
updates (no poll flicker).

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
  routes (EDA SSO pattern); UI attaches bearer when cookie exchange fails.
- **UX:** Auth failure clears table *Loading…* placeholders with a sign-in message.

## v0.0.61

**Fix standalone View-link sign-in failure (v0.0.60 regression):**

- **Root cause:** Bootstrap called `GET /api/config` first, then spent up to ~16s on
  silent-SSO retries before attempting `keycloak.login()`. With an active EDA session,
  `check-sso` often returns false in a new tab; the delay let the 20s bootstrap timeout
  fire and showed *Sign in failed* before the auto-login redirect ran.
  `redirectUri` was rebuilt from `apiBase` instead of the full `location.href`, so
  post-login token exchange could fail after redirect.
- **EDA launcher parity:** Run `keycloak.init` (`check-sso`) **before** API calls; on
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
- **EDA launcher parity:** Process keycloak-js OAuth callback before `GET /api/config`,
  retry silent SSO 3× with backoff, then at most one auto `keycloak.login()` in
  standalone tabs only (embedded never auto-login).
- **`redirectUri` fix:** Always uses registered proxy base
  `/core/httpproxy/v1/imagemanager/` (strips OAuth noise, preserves deep links).
- **No bootstrap failure banner** until silent SSO + optional auto-login are exhausted.

## v0.0.57

**Fix embedded View-link reload loop (v0.0.56 regression):**

- **Root cause:** v0.0.56 auto-called `keycloak.login()` inside the EDA embedded
  iframe when silent SSO failed. EDA external launcher uses the same fallback in a **new tab**,
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
- **EDA launcher parity:** Auto-fallback now uses `keycloak.login({ redirectUri })`
  (public `auth` client) instead of the server confidential-client redirect.
- **Loop guard:** `sessionStorage` debounce + stop auto-redirect after
  `auth_error=callback`; show recoverable **Try again** / **Sign in** banner
  instead.
- **Embedded + standalone:** Same keycloak-js login fallback (EDA catalog shows
  *Signing in…* briefly, then opens — no reload loop).

## v0.0.55

**Fix View-link sign-in UX — OIDC fallback (v0.0.54 gap):**

- **Root cause (v0.0.54):** When keycloak-js `check-sso` returned false (common even
  with a valid EDA GUI session), bootstrap called `requireSignIn()` and showed
  *Sign-in failed. Try again or use Sign in.* instead of falling through to OIDC.
  Standard keycloak-js flow calls `keycloak.login()` on the same path, which completes instantly
  when the user is already signed into EDA.
- **EDA launcher parity:** Bootstrap shows **Signing in…** immediately; silent SSO
  retries once; standalone View links fall back to `/oauth/login` (OIDC redirect)
  before any error banner. Embedded iframe still shows **Try again** only.
- **Keycloak init:** `pkceMethod: S256` and same-origin `silentCheckSsoRedirectUri`
  via `new URL("oauth/silent-sso.html", location.href)` (EDA SSO pattern).
- **Deep links:** `?return=` on `/oauth/login` preserves `?details=` (and other
  query params) through the OIDC callback redirect.

## v0.0.54

**Fix sign-in failure — restore auth bootstrap (v0.0.39 pattern):**

- **Root cause:** v0.0.40+ auto-redirected to `/oauth/login` when silent SSO failed;
  a broken OIDC callback surfaced the plain-text error *Sign-in failed: could not
  complete authentication.* instead of a recoverable in-app state. `silentSso()`
  also created a throwaway Keycloak instance (cannot re-init reliably).
- **EDA launcher parity restored:** trust `GET /api/config` 200 on bootstrap without
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

**Fix page refresh loop + live indicator on all tabs (EDA SSO pattern):**

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

**Regenerated images (cluster fix):** bundle keycloak-js in the controller image
(`/assets/keycloak.min.js`) because `/core/proxy/v1/identity/js/keycloak.min.js`
returns 404 on this EDA release. Sign-in uses keycloak-js + `POST /oauth/session`
instead of the broken server `/oauth/login` code exchange (TLS verify failure to
in-cluster Keycloak).

## v0.0.50 (original)

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
  (`window.top.location.reload()`) — no in-app Try again banner (EDA catalog
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

- **Keycloak revalidation (EDA SSO pattern):** After bootstrap (`authReady`),
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

**EDA logout sync (EDA SSO pattern, v0.0.40-safe):** After bootstrap completes
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

**Durable embedded EDA sign-in (EDA launcher parity):** Simplify auth to two clear
paths. Bootstrap: `GET /api/config` → 200 trusts `im_session` with no Keycloak;
401 runs silent SSO once, exchanges the token, then retries config (with cookie
commit retries). Periodic checks probe the server only; Keycloak runs on 401.
All auth failures show a recoverable banner with **Try again** (embedded and
standalone) — never the fatal "Sign-in failed inside EDA" table-empty state.
Explicit `credentials: "same-origin"` on session fetches. v0.0.36 upload guard
and v0.0.37 no-refresh polling unchanged.

## v0.0.38

**Fix embedded EDA sign-in regression (v0.0.37):** Restore the v0.0.35 EDA catalog
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
`onAuthLogout` / `checkLoginIframe` watchers (EDA SSO pattern). On real session
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
rounded corners); replaces the default `eda.svg`.

## v0.0.27

Browser tab favicon uses the same **`eda.svg`** Nokia connect logo as the app bar
(EDA pattern).

## v0.0.26

Remove **Sign out** from the app bar; EDA platform sign-out stays in the main GUI.

## v0.0.25

Replace the approximate Nokia wordmark with the same **`eda.svg`** connect logo
used by EDA catalog apps (served at `/assets/eda.svg`, displayed at 26px height).

## v0.0.24

Single top app bar (EDA style) — removed the stacked two-tier header
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

Event-driven dashboard sync (EDK parity) — no more polling lag:

- **Kubernetes watch on Artifact CRs:** other EDK catalog apps
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

Seamless SSO from the dashboard + EDA-style liveness columns:

- **No more Nokia EDA login page:** the fallback OIDC authorize URL now goes
  through the EDA **identity proxy** (`/core/proxy/v1/identity`) — the same
  Keycloak base the EDA GUI logs in through. Keycloak session cookies are
  scoped to that base path, so a logged-in user is 302'd straight back with a
  code (no login form). The previous URL used the Keycloak httpproxy path,
  whose cookie path never matched the GUI session, forcing a fresh login.
- **Dashboard shows app liveness (EDA launcher parity):** an always-present
  service summary row publishes `health` (Ready/Degraded) and `http`
  (Reachable/NoTLS/Down, self-reported by the serving thread) plus aggregate
  image counts — visible even with zero images, like standard EDA launcher
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
  `showInfoPanel`, so clicking a row opens EDA's info panel (EDA catalog
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

UI redesign (EDA pro look, dashboard-first):

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

Fix empty Image Manager launcher table (app-status parity):

- **Root cause:** EQL on `imagemanagerconfigs` / `imagemanagerartifacts` returns no rows — CE logs
  `InvalidNamespaceOrGvk` for cluster-scoped imagemanager CRDs, and nested
  `ImageManagerConfig.status.artifacts` is not flat-table queryable.
- Controller publishes per-artifact launcher rows to `.cluster.apps.imagemanager.status`
  via bundled `status-publisher` daemon (persistent bidi `StateDbUpdate` +
  `StreamingJsonSchema` to `eda-sa.eda-system.svc:51100` with internal mTLS,
  reverse-engineered from EDK `dbStreamHandler`).
- Dashboard EQL switched to `.cluster.apps.imagemanager.status` with columns Name (`service`),
  Status (`status`), View (`open`) — matches EDA dashlet field bindings.
- Deployment: mount internal EDA mTLS certs + trust bundle for state-aggregator access.
- `imagemanager-viewer` ClusterRole: `tableRules` for `.cluster.apps.imagemanager.**`.
- Remove 5-minute `LAUNCHER_SYNC_GRACE_SECONDS` skip (default `0`); `artifact_launcher` still
  syncs `ImageManagerArtifact` CRs every reconcile when uploads exist.

**Replace / overwrite:** When the user confirms Replace and the image already exists on the PVC,
the app now **republishes Artifact CRs from local storage** (eda-asvr re-pulls from the
controller) instead of re-downloading the URL or wiping the upload directory. Full delete
still removes PVC data via the Delete action.

**Known limitation (v0.0.10):** Launcher rows require the bundled `status-publisher`
daemon (persistent bidi `StateDbUpdate` + `StreamingJsonSchema` to `eda-sa`, EDA catalog
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

- Revert manifest `ui.category` from **System** to **Topology** (EDA catalog apps and all
  working catalog apps use Topology; `System` is not registered for custom app views —
  same failure mode as the pre-v0.0.4 custom `Image Manager` category).
- Revert launcher EQL to `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerconfigs`
  (always has a `default` row; empty `imagemanagerartifacts` list can prevent view
  registration on fresh installs).
- Regenerate dashboard UUIDs and bump dashboard `version` to `0.0.8`.
- Keep `icon: CloudUpgrade` and catalog structural clone (`flexRow` → `dashletDataView`).

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

Rebuild EDA launcher dashboard from catalog reference (v0.2.2):

- Structural clone of reference dashboard JSON with fresh UUIDs (no reuse from prior imagemanager).
- EQL on `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerartifacts` with columns Name, Size, Status, View.
- Manifest view icon changed from `Import` to `CloudUpgrade` (`ui.category: Topology`, view component last).

## v0.0.4

Fix missing EDA nav view (entire Image Manager panel absent):

- Restructure `imagemanager-dashboard.json` as a catalog structural clone
  (`flexRow` → `dashletDataView`, external HttpProxy nav target) using simpler
  EQL on `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerconfigs`
  (always has a `default` row) instead of `imagemanagerartifacts` (empty list
  may fail view registration).
- Move manifest `view` component to last (EDA SSO pattern: workloads before view).
- Register nav under `ui.category: Topology` (EDA catalog uses Topology; custom
  `Image Manager` category never appeared in the nav tree).
- Match EDA catalog manifest view section field order (`category`, `icon`, `name`).
- Add `status.open: View` on ImageManagerConfig for launcher View column parity.
- Regenerate dashboard UUIDs and bump dashboard `version` to `0.0.4`.

## v0.0.3

Install/uninstall reliability aligned with EDA catalog patterns:

- Reorder manifest components: CRDs → RBAC → PVC → Service → Deployment → HttpProxy → DaemonSet (Deployment was previously applied before ServiceAccount/RBAC existed).
- Remove hardcoded `ghcr-imagemanager` imagePullSecret (EDA injects `appstore-eda-apps-registry-image-pull`; the missing secret caused install warnings and pull failures).
- Graceful controller shutdown: `preStop` sleep, `stop_file_server()` on SIGTERM, probes aligned with EDA catalog (`initialDelaySeconds`, no TCP startupProbe).
- DaemonSet `preStop` removes containerd registry redirect on uninstall so reinstall is not blocked by stale `hosts.toml`.
- Fix invalid `namespace` field on cluster-scoped `imagemanager-viewer` ClusterRole.
- Add `progressDeadlineSeconds: 600` and app labels on workloads/PVC/HttpProxy.

## v0.0.2

Fix EDA nav launcher dashboard after the v0.0.1 release reset:

- Restore EDA-style dashboard JSON (`flexRow` → `dashletDataView`, external
  HttpProxy nav target) with flat EQL on `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerartifacts` (not broken `status.artifacts` nested paths).
- Regenerate dashboard UUIDs so EDA re-registers the view after the semver downgrade from v0.0.7 → v0.0.1 left a stale/missing nav entry.
- Confirm manifest bundles the `view` component and `imagemanager/ui` dependency; controller continues syncing `ImageManagerArtifact` launcher rows.

## v0.0.1

Initial public release (Image Manager for EDA):

- Web UI to upload SR Linux, SR OS hardware, and SR-SIM zips; automatic type detection, md5, and YANG schema profile resolution (schema-profiles or on-the-fly from `nokia/7x50_YangModels`).
- Controller file server, Artifact CR management, PVC-backed storage, and NodeProfile snippet helpers.
- EDA launcher dashboard with cluster-scoped `ImageManagerArtifact` CRs (flat status column bindings for EDA EQL).
- Offline air-gap bundle attached to each GitHub Release under `apps/imagemanager.eda.edacommunity.com/<version>`.
