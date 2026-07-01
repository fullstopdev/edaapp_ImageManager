# Changelog

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
