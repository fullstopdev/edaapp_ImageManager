# Improvement prompt — `fullstopdev/edaapp_ImageManager`

Paste this whole prompt into a Claude Code session opened at the repo root
(`edaapp_ImageManager/`). It's ordered by priority; each section is
independently actionable so you can run them as separate sessions/PRs if you
prefer smaller diffs.

Context for whoever runs this: this is a Nokia EDA application (Python
stdlib-only controller + a single-file HTML/CSS/JS web UI) that lets users
upload SR Linux / SR OS / SR-SIM vendor images through a browser and turns
them into EDA `Artifact` CRs. Reference sibling app for UI/UX parity is
`cable-map` (`ghcr.io/eda-labs/cable-map:v0.2.2`). Read
`docs/CABLE-MAP-UI-COMPARISON.md` and `docs/STABILITY.md` before starting —
they document real incidents already fixed and should not be re-litigated.

---

## 0. Housekeeping before touching code

1. `docs/CABLE-MAP-UI-COMPARISON.md` section 4/6 still says the
   `imagemanager-viewer` ClusterRole and the cable-map-style dashboard JSON
   are "missing." Both now exist (`imagemanager/manifests/eda_viewer_role.yaml`,
   `imagemanager/ui/imagemanager-dashboard.json`). Update that doc to say
   "done in vX.Y.Z" instead of "missing," so it stops reading as an open
   action item to the next person/session.
2. Confirm `imagemanager/manifest.yaml` `spec.image` tag, `pyproject.toml`
   version, and the dashboard JSON's `version`/`lastChanged` are all bumped
   together before any release — add a one-line pre-publish checklist item
   for this if it isn't already in `Makefile`/CI.

## 1. Test coverage for the controller (highest priority)

`common/` and `utils/` in this repo have real `test_*.py` files
(`test_component.py`, `test_metadata.py`, `test_interface.py`, `test_ip.py`,
etc.), but every file under `imagemanager/build/controller/` —
`main.py`, `webui.py`, `uploads.py`, `import_common.py`, `fileserver.py`,
`auth.py`, `k8s.py`, `imports.py`, `nodeagent.py`, `artifact.py`,
`schemaprofile.py`, `app_status.py`, `artifact_launcher.py` (8,200+ lines
total) — has zero test coverage, and CI (`.github/workflows/publish.yml`)
runs no lint or test step before build/publish.

Do the following, in order:

1. **Add a `test/` (or `imagemanager/build/controller/tests/`) directory**
   mirroring the style already used in `common/test_component.py` and
   `utils/test_interface.py` — plain `unittest`/`pytest`, no new
   dependencies beyond what's in `pyproject.toml`'s `dev` group.
2. **Prioritize pure-logic functions first** — these need no mocking and
   give the fastest coverage-per-effort:
   - `uploads.py`: `sanitize_filename`, `derive_name`, `to_k8s_name`,
     `looks_like_zip`, `parse_md5_text`, `parse_md5sums`, `_norm_md5_path`,
     `detect_nos_from_zip`, `detect_sros_version`, `normalize_license`,
     `is_valid_license`, `detect_license_nos`, `_parse_oci_layout`.
   - `fileserver.py`: `_within_upload_grace`, `_resolve_download_status`,
     `_aggregate_download_status`, `nos_label`, `_infer_nos_from_repo`.
   - `import_common.py`: `collect_artifact_names`, `_artifact_names_for_upload`.
   - `auth.py`: `_decode_jwt`, `token_identity`, `is_allowed`,
     `has_idp_session_cookie`, `jwt_exp`, `session_cookie_max_age`.
3. **Mock the K8s boundary, not the business logic.** `k8s.py`'s
   `_request` is the single chokepoint for every cluster call — wrap it
   behind a fake/in-memory implementation in tests so `import_common.py`'s
   `_process_srl` / `_process_sros` / `_process_srsim` /
   `reconcile_local_uploads` can be exercised without a live cluster.
   Use fixture zip files (a few KB, synthetic, not real vendor images) for
   `extract_image_from_zip` / `extract_sros_images` / `extract_srsim_image`.
4. **Add regression tests for the two documented incident classes** in
   `docs/STABILITY.md` so they can't silently regress:
   - reconcile-storm guard (unconditional status PUT skipped when payload
     SHA-256 unchanged),
   - node-agent DaemonSet label/teardown behavior.
5. **Wire ruff + pytest into `.github/workflows/publish.yml`** (or a new
   `ci.yml` that runs on PRs) as a required check *before* the
   build/push/publish job, not after. Use the existing `ruff.toml` config —
   don't introduce a second lint config.
6. Target: enough coverage that a future session can run
   `pytest imagemanager/build/controller -q` and trust a green run before
   touching `main`.

## 2. Security hardening pass on `auth.py`

1. `_decode_jwt` currently base64-decodes the JWT payload without verifying
   the signature, issuer, or audience. Because the access token comes from
   a server-side confidential-client code exchange with Keycloak over TLS
   (not something a browser hands you directly), this is lower-risk than a
   typical "trust a client-supplied JWT" bug — but role-based authorization
   (`is_allowed`) depends entirely on the payload's `realm_access.roles`
   claim being what Keycloak actually issued. Add explicit verification:
   fetch Keycloak's JWKS once (cache with TTL), verify signature + `exp` +
   `iss` + `aud`/`azp` match the configured client, and reject anything
   that fails rather than silently trusting a malformed/expired-looking
   payload.
2. Confirm `_client_secret` / `_kc_admin_token` never log the secret value
   even at debug level — grep for `print(`/`log.debug` near these
   functions and redact if found.
3. Add a short `SECURITY.md` (or a section in `docs/STABILITY.md`)
   documenting the trust boundary explicitly: browser → EDA identity
   proxy → this app's `auth.py` → Keycloak, and which hop is responsible
   for which validation. This matters because the next person touching
   `auth.py` won't have this conversation's context.

## 3. Split `webui.py` for maintainability

`webui.py` is a single 2,513-line Python module holding one giant
`INDEX_HTML` triple-quoted string (HTML + CSS + JS all inline, no build
step). This works and matches the "self-contained, no external assets"
design goal stated in its own docstring — keep that constraint, don't
introduce a bundler/npm build step, since the whole point is a
zero-dependency stdlib controller. Instead:

1. Split the single string into three Python constants assembled at import
   time: `_STYLE_CSS`, `_APP_JS`, `_BODY_HTML`, each as its own
   triple-quoted string, composed into `INDEX_HTML` at the bottom of the
   file. This alone makes diffs reviewable (a CSS-only change won't show
   up as a diff against JS lines) without changing runtime behavior at all.
2. If the JS portion keeps growing, consider moving it to its own
   `imagemanager/build/controller/static/app.js` file loaded via
   `importlib.resources` or read-once-at-startup — still self-contained
   (ships inside the same container image), still no external CDN/asset
   dependency, but editable/lintable as real JavaScript. Only worth doing
   if you're going to keep adding UI features; skip if the file is close
   to feature-complete.
3. Add `eslint`-via-`npx` (dev-only, not a runtime dependency) or at
   minimum a `node --check` smoke test in CI that extracts the JS block
   and confirms it parses, so a typo in the embedded JS doesn't ship
   silently (there's no browser test today that would catch it).

## 4. `uploads.py` decomposition (969 lines, several unrelated concerns)

Split along these natural seams, keeping all existing public function
names as re-exports so `import_common.py`/`fileserver.py` callers don't
need changes in the same PR:

- `zip_extract.py` — `detect_nos_from_zip`, `extract_image_from_zip`,
  `detect_sros_version`, `extract_sros_images`, `extract_srsim_image`,
  `_parse_oci_layout`, `_srsim_member`.
- `licensing.py` — `normalize_license`, `is_valid_license`,
  `detect_license_nos`, `license_cm_name`, `set_license_meta`,
  `store_license_file`.
- `storage.py` — `stream_upload`, `_copy_streaming`, `_trim_write_cache`,
  `disk_usage`, `storage_stats`, `upload_dir_size`,
  `cleanup_stale_work_dirs`, `count_work_dirs`, `_work_dir_is_empty`,
  `_dir_age_seconds`, `scan_incomplete_dirs`, `wipe_all_uploads`.
- `metadata.py` (upload-tracking, not to be confused with
  `common/metadata.py`) — `read_meta`, `list_meta`, `rewrite_meta`,
  `finalize_upload`, `finalize_group`, `delete_upload`,
  `upload_has_local_bytes`.

This is a pure refactor — no behavior change — so it's a good candidate to
do *after* section 1's tests exist, so the refactor has a safety net.

## 5. Observability / operational polish

1. `main.py`'s reconcile loop already has backoff and change-detection
   (per `docs/STABILITY.md` v0.0.7/v0.0.9 notes) — good. Add a Prometheus
   `/metrics` endpoint (stdlib-only counter/gauge implementation, no
   `prometheus_client` dependency needed given the "stdlib only" house
   style) exposing: reconcile duration, reconcile failures, active
   uploads, storage bytes used/free, node-agent heartbeat age. This gives
   you the same kind of visibility you built for the EDA telemetry lab
   Grafana dashboard, but for this app's own health.
2. `docs/STABILITY.md`'s "Optional future work" list already names
   "controller watch informers (replace polling)" — if reconcile load
   ever becomes a real issue at scale, this is the correct next step
   (watch + resourceVersion, not more frequent polling). Not urgent given
   current 60s interval and documented low CPU usage; keep it on the
   backlog, don't do it speculatively.

## 6. Documentation

1. Once section 1 lands, add a "Running the tests" section to `README.md`
   (`pip install -e . --group dev && pytest imagemanager/build/controller`).
2. Update `docs/CABLE-MAP-UI-COMPARISON.md` per item 0.1 above.
3. `CHANGES-imageimport.md` and `imagemanager/docs/CHANGELOG.md` — confirm
   there's exactly one changelog of record; having both risks drift. If
   `CHANGES-imageimport.md` is legacy, fold its still-relevant history into
   the CHANGELOG and mark it archived at the top rather than deleting
   history.

---

## How to work through this

Recommended order for separate sessions/PRs:
1. Section 1 (tests) — unlocks safe refactors everywhere else.
2. Section 2 (auth hardening) — security, do it early, it's self-contained.
3. Section 0 + 6 (docs) — cheap, do alongside whichever PR touches the
   relevant file.
4. Section 3 and 4 (refactors) — do after tests exist.
5. Section 5 (metrics) — whenever there's an operational reason to want it.

For every PR: keep diffs scoped to one section, run `ruff check` and the
new `pytest` suite locally before pushing, and bump
`imagemanager/manifest.yaml` `spec.image` + the dashboard JSON `version`
only on releases, not on every commit.
