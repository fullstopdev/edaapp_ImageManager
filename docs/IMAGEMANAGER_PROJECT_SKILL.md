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
- `docs/CABLE-MAP-UI-COMPARISON.md` — a point-in-time (2026-07-01)
  research doc comparing this app's launcher/dashboard/HttpProxy pattern
  against the reference sibling app `cable-map`. Treat it as history, not
  a live spec — check current manifests before assuming something in it
  is still true.
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
  requested.
- **Cable-map is the UI/UX and manifest reference**, not a library to
  import from. When something looks inconsistent between this app and
  cable-map (dashboard JSON shape, HttpProxy setup, ClusterRole shape),
  check the *current* cable-map OCI image/catalog before assuming the
  comparison doc is still accurate — it may already have been reconciled.
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

## Auth / SSO (cable-map aligned, v0.1.37+)

Session model matches cable-map:

1. EDA Keycloak browser session (identity proxy `/core/proxy/v1/identity`)
2. SPA: `keycloak-js` public client `auth` + same-origin `silent-check-sso.html`
3. `POST /oauth/session` — bearer token → JWKS + Keycloak userinfo validation → `im_session` cookie
4. `/api/*` gated on `im_session`; shell (`GET /`) loads without cookie
5. Bootstrap: when `/api/config` returns 200, `keycloak-js` `check-sso` must confirm a live
   EDA session before `onAuthReady` (stale 8h `im_session` alone is not enough)
6. EDA logout: periodic `reconcileAuthState` (3s, including hidden tabs) uses `check-sso`
   plus identity probes; clears `im_session` server-side on failure
7. Server `/oauth/login` (confidential `eda` client) remains as OIDC fallback

Do **not** require identity-proxy cookies in `auth.verify_session` (scoped to
`/core/proxy/v1/identity`, not the httpproxy path). Do **not** fail bootstrap
solely on inconclusive identity probes (403) — trust `keycloak.authenticated`
from `check-sso` to avoid the v0.1.35 OAuth loop.

## Workflow expectations

- The user applies files, pushes to GitHub, and expects a fresh clone +
  continuation from the latest `main` each session — don't assume state
  from a previous conversation without re-cloning/re-viewing first.
- CI is `.github/workflows/publish.yml` (build/push/publish only, no
  lint/test gate today) and `delete-ghcr-packages.yml`. Any CI change
  should be additive (a new required check) rather than replacing the
  existing publish flow.
