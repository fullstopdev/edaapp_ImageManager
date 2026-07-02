# Changelog

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
