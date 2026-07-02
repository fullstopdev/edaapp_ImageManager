# Image Manager stability notes

Research and fixes: 2026-07-01. Reference app: **cable-map** (`ghcr.io/eda-labs/cable-map:v0.2.2`).

## What was going wrong

### Install / uninstall (v0.0.2 and earlier)

| Symptom | Root cause | Fixed in |
|---------|------------|----------|
| Install fails or EDA transaction errors | Deployment applied before ServiceAccount/RBAC | v0.0.3 |
| `FailedToRetrieveImagePullSecret ghcr-imagemanager` | Hardcoded pull secret that does not exist | v0.0.3 |
| Stuck terminating pod / probe failures on upgrade | No graceful HTTPS shutdown on SIGTERM | v0.0.3 |
| SR-SIM pulls fail after reinstall | DaemonSet `hosts.toml` redirect left on nodes | v0.0.3 (`preStop` cleanup) |
| Node-agent pod survives app uninstall | DaemonSet pod template lacked `eda.nokia.com/app: eda-imagemanager`; blocking `preStop` delayed teardown | **v0.0.7** |
| CE pod crash on v0.0.8 install; no dashboard | `ImageManagerArtifact` CRD had no `spec` schema; CE `propertiesBackwardCompatible` nil-deref | **v0.0.9** |
| Invalid ClusterRole admission noise | `namespace` on cluster-scoped `imagemanager-viewer` | v0.0.3 |

### Runtime / cluster load (v0.0.6 and earlier)

| Symptom | Root cause | Fixed in |
|---------|------------|----------|
| API `429 storage is (re)initializing` on startup | Launcher sync lists CRDs while etcd is still warming; no retry | **v0.0.7** |
| Reconcile storm / API hammering | 30s loop + unconditional status PUT + 5s UI polling listing all Artifacts | **v0.0.7** |
| Upload UI stalls during URL import | `imports.reconcile()` ran synchronously in main loop (large downloads) | **v0.0.7** |
| Node-agent touches every node every 60s | DaemonSet required for SR-SIM only; frequent resync | **v0.0.7** (optional / slower) |
| Brief proxy outage on upgrade | `Recreate` + RWO PVC (required — two pods cannot mount the claim) | Documented; cable-map uses same pattern |

Observed on the lab cluster (2026-07-01): no OOM kills; controller reconcile ~120–250ms/cycle at v0.0.4; repeated pod `Killing` events during upgrades are expected with `Recreate`.

## v0.0.7 mitigations

1. **K8s client retries** — `k8s._request()` backs off on HTTP 429/5xx (etcd init, overload).
2. **Slower, smarter reconcile** — default interval **60s** (`RECONCILE_INTERVAL` env); skip ImageManagerConfig status PUT when payload unchanged (SHA-256).
3. **Non-blocking imports** — `ImageImport` URL downloads run in a background thread.
4. **UI/API cache** — `build_tracked_list()` cached 8s; Status tab polls every **10s** (was 5s).
5. **Safer node-agent** — `NODE_AGENT_ENABLED=false` skips all `hosts.toml` writes (heartbeat only); default resync **120s**; App Store setting **Enable SR-SIM node agent** (`nodeAgentEnabled`); scale DaemonSet to 0 when SR-SIM is unused:
   ```bash
   kubectl scale daemonset eda-imagemanager-node-agent -n eda-system --replicas=0
   ```
6. **Clean uninstall** — DaemonSet pod template labels match Deployment (`eda.nokia.com/app: eda-imagemanager` + `eda.nokia.com/component: node-agent`); removed blocking `preStop`; `terminationGracePeriodSeconds: 10`. Manual cleanup if upgrading from v0.0.6:
   ```bash
   kubectl delete daemonset eda-imagemanager-node-agent -n eda-system --ignore-not-found
   ```
7. **Resource limits** — unchanged from v0.0.3+ (controller 256Mi/512Mi; node-agent 32Mi/128Mi), aligned with cable-map discipline.

## v0.0.9 mitigations

1. **CE install crash fix** — empty `ImageManagerArtifactSpec` in CRD/OpenAPI so manifest backward-compat checks succeed.
2. **Startup grace** — controller waits **45s** before first reconcile (`STARTUP_DELAY_SECONDS`).
3. **Error backoff** — reconcile interval doubles on consecutive failures (cap `MAX_RECONCILE_BACKOFF`, default 300s).
4. **Deferred launcher sync** — skip `ImageManagerArtifact` CR sync for **5m** when there are no uploads (`LAUNCHER_SYNC_GRACE_SECONDS`).
5. **Node-agent init** — DaemonSet init container waits for controller `/healthz` before writing containerd redirects.

## Cable-map vs Image Manager (complexity)

| Area | Cable Map v0.2.2 | Image Manager v0.0.7 |
|------|------------------|----------------------|
| Controller | Go operator (single binary) | Python controller (stdlib + threads) |
| CRDs | None | 3 (Config, Import, Artifact mirror) |
| Extra workloads | None | Optional DaemonSet (SR-SIM registry redirect) |
| Storage | None | 20Gi RWO PVC |
| Pod count | 1 | 1 + 1/node (or 0 if DS scaled down) |
| Deployment strategy | Recreate | Recreate (PVC-bound) |
| Probes | HTTP `/healthz` 5s/10s | HTTPS `/healthz` 5s/10s |
| Reconcile | Operator watch + periodic | Poll every 60s |
| Host filesystem | None | `hostPath` containerd config (node-agent only) |

Image Manager is intentionally heavier (upload store + artifact orchestration + optional node registry redirect). v0.0.7 keeps that scope but reduces API churn and makes the DaemonSet optional for labs that only upload SR Linux / SR OS hardware images.

## Graceful shutdown (verify)

Controller (`main.py`):

- `preStop: sleep 5` on Deployment
- SIGTERM → `shutdown_event` → `fileserver.stop_file_server()` (probe sees `shutting_down`)

Node-agent (`nodeagent.py`):

- SIGTERM handler calls `cleanup()` (removes `hosts.toml`); no blocking `preStop` hook

## Optional future work

- Talos / immutable nodes: document `machine.registries` mirror instead of DaemonSet.
- Controller watch informers (replace polling) if API load remains an issue at scale.
- Separate launcher sync from main reconcile (already partially deduplicated).
- RollingUpdate via ReadWriteMany PVC or object storage backend (remove Recreate downtime).
- Port controller hot paths to Go only if Python CPU becomes a bottleneck (not required today).
