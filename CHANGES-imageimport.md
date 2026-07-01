# Changes in this checkout vs. upstream kkayhan/edaapp_ImageManager

Adds a declarative `ImageImport` CRD (import an image by URL from EDA's
native resource UI, with live status columns) and the missing nav/launcher
entry for the existing upload SPA.

## New files
- `imagemanager/api/v1alpha1/imageimport_api_types.go` — Spec/Status types
- `imagemanager/api/v1alpha1/imageimport_base_types.go` — Kind/List types + printer columns
- `imagemanager/crds/imagemanager.eda.edacommunity.com_imageimports.yaml` — CRD
  (hand-written to match controller-gen's expected output; regenerate via
  `make imagemanager-generate` after the Go types are in place, and diff the
  result against this file before trusting it further)
- `imagemanager/build/controller/import_common.py` — shared zip-processing +
  license logic (extracted out of fileserver.py's HTTP handlers)
- `imagemanager/build/controller/imports.py` — ImageImport reconciler
- `imagemanager/ui/imagemanager-launcher.json` — launcher view for the SPA

## Modified files
- `imagemanager/manifest.yaml` — registers the new CRD + `view` component;
  also moved appInfo.categories from `integrations` to `networking`
- `imagemanager/manifests/rbac.yaml` — RBAC for `imageimports`(`/status`) +
  scoped `secrets: get` (for `licenseKeySecretRef`)
- `imagemanager/build/controller/main.py` — calls `imports.reconcile()` each cycle
- `imagemanager/build/controller/k8s.py` — added `update_namespaced_cr_status()`
- `imagemanager/build/controller/fileserver.py` — refactored to call
  `import_common.process_zip()` / `import_common.attach_license()` instead of
  duplicating that logic, so the browser-upload path and the new CRD path can
  never drift apart. All edits verified with `python3 -m py_compile`.

## ⚠️ Not verified: the `view` component schema
`imagemanager-launcher.json`'s shape (`type`/`title`/`url`/`sameOrigin`) is a
best-effort reconstruction, not a confirmed schema — see the `"//"` comment
inside that file for why, and confirm against docs.eda.dev or a live
installed app before publishing.

## Before building
Run `make imagemanager-generate` (regenerates CRD yaml/OpenAPI JSON/pysrc/
deepcopy from the new Go types) and diff its output against the hand-written
CRD yaml here, then `make imagemanager-build-push` as usual.

## Release versioning

App releases use semver (semver patch bumps (`v0.0.2`, …) after the initial `v0.0.1` release). Bump `imagemanager/manifest.yaml` `spec.image`, controller manifests, and `imagemanager/build/controller/main.py` `VERSION` before merging to `main`. Catalog tags are `apps/imagemanager.eda.edacommunity.com/<version>`.
