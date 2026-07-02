# Changelog

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
