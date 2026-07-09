# Project skill card — `fullstopdev/edaapp_ImageManager`

Keep this at the top of any future session on this repo (Claude Code or
chat) so behavior stays consistent across sessions.

## What this is

A Nokia EDA application. Users upload SR Linux / SR OS / SR-SIM vendor
`.zip` images through a browser; the controller unpacks them, creates EDA
`Artifact` CRs, and (for SR OS/SR Linux) resolves a matching YANG schema
profile automatically. Runs as one pod (+ optional per-node DaemonSet for
SR-SIM registry redirect) inside an EDA cluster.

## Repo layout (what lives where)

- `imagemanager/build/controller/` — the actual running app. Python
  **stdlib only**, no pip dependencies at runtime. This is where almost
  all feature work happens:
  - `main.py` — entrypoint, reconcile loop, signal handling.
  - `webui.py` — the entire single-page web UI (HTML/CSS/JS as one Python
    string, self-contained, no external assets, no CDN, no build step).
  - `fileserver.py` — embedded HTTPS server (port 8443), serves the UI to
    browsers and files to `eda-asvr`.
  - `uploads.py` — zip parsing/extraction, upload streaming, license
    handling, on-disk metadata tracking.
  - `import_common.py` — shared image-import logic (upload dialog +
    `ImageImport` CR reconcile both funnel through here).
  - `auth.py` — server-side OIDC (Keycloak) login, session cookies,
    role-based gating.
  - `k8s.py` — raw urllib-based Kubernetes API client (no `kubernetes`
    pip package).
  - `imports.py`, `nodeagent.py`, `artifact.py`, `schemaprofile.py`,
    `app_status.py`, `artifact_launcher.py` — CRD reconcilers and
    supporting pieces.
- `imagemanager/crds/`, `imagemanager/manifests/`, `imagemanager/ui/`,
  `imagemanager/settings/` — the EDA app package: CRD YAML, RBAC/
  Deployment/Service/HttpProxy manifests, the dashboard/launcher view
  JSON, install-time App Store settings.
- `imagemanager/api/v1alpha1/pysrc/` — **auto-generated** from the Go
  `_types.go` files by `edabuilder create`/`generate`. Never hand-edit
  these; regenerate instead.
- `common/`, `utils/`, `test/` — shared library code used across multiple
  Nokia EDA app repos (not imagemanager-specific), with real
  `test_*.py` unit test coverage already in place. This is the style to
  match when adding tests under `imagemanager/build/controller/`.
- `docs/STABILITY.md` — incident log + fixes (install/uninstall races,
  reconcile storms, node-agent teardown). Read before touching
  `main.py`'s reconcile loop, `nodeagent.py`, or any RBAC/manifest file —
  several of these were hard-won fixes and shouldn't be casually reverted.

## House style / constraints to respect

- **Stdlib-only controller.** No new pip runtime dependencies in
  `imagemanager/build/controller/`. `ruff` is the only dev dependency
  (see `pyproject.toml` `dev` group). If a task seems to need a pip
  package, first check whether it can be done with stdlib (`urllib`,
  `http.server`, `ssl`, `hashlib`, `zipfile`, `threading`) — that's the
  existing pattern throughout `k8s.py`, `auth.py`, `fileserver.py`.
- **UI is one self-contained Python string.** `webui.py`'s `INDEX_HTML`
  intentionally has no external JS/CSS assets and no build step (no npm,
  no bundler). Preserve that when editing — don't introduce a
  React/Vite pipeline here even though other Nokia EDA projects (e.g.
  the resource-browser SvelteKit app) do use one. Splitting the single
  string into a few composed constants for reviewability is fine and
  encouraged; adding a JS framework/build step is not, unless explicitly
  requested. UI styling uses `:root` design tokens (`--space-*`, `--text-*`)
  and a hidden SVG icon sprite (`<use href="#icon-*">`) — extend those
  patterns rather than adding new inline SVG blobs.
- **EDA launcher conventions** — dashboard JSON (`flexRow` → `dashletDataView`),
  HttpProxy routing, and `imagemanager-viewer` ClusterRole should match
  current EDA catalog patterns. Check live manifests and sibling apps in
  the catalog before changing launcher shape.
- **`edabuilder create`/`generate` own `imagemanager/api/**/pysrc/`.**
  Regenerate, don't hand-edit, when the underlying `_types.go` changes.
- **Versioning discipline on release:** `imagemanager/manifest.yaml`
  `spec.image` tag, `pyproject.toml` version, and
  `imagemanager/ui/imagemanager-dashboard.json`'s `version`/`lastChanged`
  should move together. `edabuilder publish` creates the git tag
  `apps/imagemanager.eda.edacommunity.com/<version>`.
- **No test suite yet for the controller** (as of this writing) — if
  asked to add a feature to `uploads.py`/`import_common.py`/`fileserver.py`
  /`auth.py`, prefer adding a small `test_*.py` alongside it in the style
  already used under `common/` and `utils/`, rather than leaving it
  untested like the rest of the controller. See
  `IMAGEMANAGER_IMPROVEMENT_PROMPT.md` section 1 for the fuller plan.
- **Complete files over diffs/descriptions** — when asked to change a
  controller file, return the full updated file (or a precise patch),
  not a prose description of the change, matching how this project has
  been worked on so far.

## Auth / SSO (v0.1.37+)

Image Manager uses the standard EDA silent SSO stack: embedded SPA with
`keycloak-js` 26.x, public browser client `auth`, and server-side OIDC fallback.

Session model:

1. EDA Keycloak browser session (identity proxy `/core/proxy/v1/identity`)
2. SPA: `keycloak-js` public client `auth`, `silentCheckSsoRedirectUri` at
   `{apiBase}/oauth/silent-check-sso.html` (same-origin asset, CSP `script-src 'self'`)
3. `keycloak.init` / `keycloak.login` use `loginRedirectUri()` = current app URL
   with OAuth query noise stripped
4. `checkLoginIframe: true` in standalone tabs; disabled in EDA iframe embed
5. `POST /oauth/session` — bearer token → JWKS + Keycloak userinfo → `im_session` cookie
6. `/api/*` also accepts live Keycloak bearer tokens when cookie exchange lags
7. Server `/oauth/login` (confidential `eda` client) remains OIDC fallback after
   `keycloak.login()` failure
8. Bootstrap: `GET /api/config` first on normal load; valid `im_session` → immediate
   `onAuthReady` with keycloak validation deferred to background (v0.1.43+). OAuth callback
   still runs keycloak `login-required` prelude. Attempt `check-sso` before config only on
   401 / stale-session paths; stale `im_session` cleared when `check-sso` returns false;
   timeout guards prevent infinite *Checking session…*; fresh sign-in skips redundant
   background check-sso (v0.1.44). Embedded iframe: immediate silent SSO on 401 when
   `kc-*` localStorage present; sign-in banner only after SSO fails (v0.1.45).
9. EDA logout: `reconcileAuthState` (3s) uses `check-sso` + identity probes

Do **not** require identity-proxy cookies in `auth.verify_session`. Do **not** fail
bootstrap solely on inconclusive identity probes (403) — trust `keycloak.authenticated`
from `check-sso` when it returns true.

## Workflow expectations

- The user applies files, pushes to GitHub, and expects a fresh clone +
  continuation from the latest `main` each session — don't assume state
  from a previous conversation without re-cloning/re-viewing first.
- CI is `.github/workflows/publish.yml` (build/push/publish only, no
  lint/test gate today) and `delete-ghcr-packages.yml`. Any CI change
  should be additive (a new required check) rather than replacing the
  existing publish flow.
