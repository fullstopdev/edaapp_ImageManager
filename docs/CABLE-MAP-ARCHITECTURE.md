# Cable Map vs Image Manager — install architecture

Research date: 2026-07-01. Sources: `eda-labs/catalog` (`apps/cable-map.eda.labs`),
OCI `ghcr.io/eda-labs/cable-map:v0.2.2` (CR/view blobs via `crane blob`), live cluster
objects, and this repo's `imagemanager/` tree.

## Executive summary

Cable Map is the reference EDA app for a minimal, reliable install footprint: CRDs are
not required, components are ordered identity → workload → routing → view, the
Deployment uses `Recreate` with standard HTTP probes, and EDA injects registry pull
secrets. Image Manager v0.0.2 violated several of these patterns (RBAC after Deployment,
missing imagePullSecret, no graceful shutdown, DaemonSet hostPath without cleanup),
which caused install/uninstall failures and EDA transaction errors.

v0.0.3 aligns Image Manager with cable-map where applicable while keeping imagemanager-specific
CRDs, PVC, and the node-agent DaemonSet.

**v0.0.4** fixes the missing EDA nav panel: register the view under `ui.category: Topology`
(not a custom top-level category), move the `view` component last in the manifest, and point
the launcher dashlet at `.cluster.imagemanager.eda.edacommunity.com.v1alpha1.imagemanagerconfigs`
(always has a `default` row).

---

## Component comparison

| Area | Cable Map | Image Manager (v0.0.3) |
|------|-----------|------------------------|
| **CRDs** | None | 3 (Config, Import, Artifact launcher) |
| **Component order** | Deployment+SA → access → Service → HttpProxy → view | CRDs → view → RBAC → PVC → Service → Deployment → HttpProxy → DaemonSet |
| **Deployment strategy** | `Recreate` (replicas=1) | `Recreate` (required for RWO PVC) |
| **PVC** | None | `imagemanager-data` 20Gi RWO |
| **DaemonSet** | None | `eda-imagemanager-node-agent` — per-node containerd `hosts.toml` redirect for SR-SIM pulls |
| **Pod count (typical)** | 1 Deployment pod | 1 Deployment pod **+** 1 DaemonSet pod per node |
| **imagePullSecrets** | EDA-injected (`appstore-eda-apps-registry-image-pull`) | Removed hardcoded secret; EDA injects |
| **Probes** | HTTP `/healthz`, readiness 5s / liveness 10s | Same pattern (HTTPS on 8443) |
| **preStop** | None in OCI | `sleep 5` on controller; DaemonSet removes `hosts.toml` |
| **HttpProxy** | `authType: atDestination`, plain HTTP backend | Same auth; HTTPS backend (cert-manager CSI) |
| **EDA ClusterRole** | `cable-map-viewer` with `urlRules` + `tableRules` | `imagemanager-viewer` (fixed: no invalid `namespace`) |
| **Graceful shutdown** | Go operator (standard SIGTERM) | Python: SIGTERM → `stop_file_server()` |

---

## Cable-map patterns adopted

1. **Install ordering** — ServiceAccount and RBAC before Deployment; PVC and Service before
   Deployment consumes them.
2. **Registry auth** — Do not reference a non-existent pull secret; let EDA patch manifests.
3. **Probes** — HTTP(S) `/healthz` with `initialDelaySeconds` (no aggressive TCP startupProbe).
4. **Single-replica Recreate** — Accept brief downtime on upgrade; required when mounting RWO PVC.
5. **progressDeadlineSeconds: 600** — Avoid indefinite stuck rollouts.
6. **Labels** — `eda.nokia.com/app` / `app-group` on workloads for traceability.
7. **HttpProxy cleanup** — Cluster-scoped CR with app labels; no finalizers; EDA removes on uninstall.

---

## Image-manager-specific concerns

| Concern | Mitigation in v0.0.3 |
|---------|----------------------|
| **RWO PVC blocks parallel pods** | Keep `Recreate`; PVC recreated on reinstall if prior claim deleted |
| **DaemonSet hostPath writes** | `preStop` + SIGTERM cleanup removes `hosts.toml` redirect |
| **Controller HTTPS thread** | `stop_file_server()` on SIGTERM so probes fail cleanly during drain |
| **ClusterRole metadata** | Removed erroneous `namespace` on cluster-scoped `imagemanager-viewer` |
| **CRD race on install** | CRDs remain first in manifest component list |

---

## Root causes of v0.0.2 install/uninstall crashes

1. **RBAC ordering** — Deployment referenced `eda-imagemanager` ServiceAccount before `rbac.yaml` created it.
2. **Missing imagePullSecret** — `ghcr-imagemanager` does not exist; kubelet logged `FailedToRetrieveImagePullSecret`.
3. **No graceful shutdown** — SIGTERM stopped reconcile loop but left HTTPS server running; `preStop` absent.
4. **DaemonSet orphan state** — `hosts.toml` redirect persisted on nodes after uninstall, confusing reinstall.
5. **Invalid ClusterRole** — `namespace: eda-system` on a cluster-scoped EDA `ClusterRole` may confuse the API admission layer.

---

## OCI layout (both apps)

Both publish as `application/vnd.nokia.eda.apps.root.v1` with layered components:

- `application/vnd.nokia.eda.apps.component.cr.v1` — K8s/EDA YAML (cable-map: 4 files in one manifest)
- `application/vnd.nokia.eda.apps.component.view.v1` — dashboard JSON
- `application/vnd.nokia.eda.apps.dependency.container.v1` — runtime image (cable-map bundles Go operator)

Image Manager additionally ships CRD and OpenAPI layers per component.

---

## References

- Cable-map catalog: `eda-labs/catalog/apps/cable-map.eda.labs/manifest.yaml`
- Cable-map OCI CR blobs: `deployment.yaml`, `access.yaml`, `service.yaml`, `httpproxy.yaml`
- UI comparison: [CABLE-MAP-UI-COMPARISON.md](./CABLE-MAP-UI-COMPARISON.md)
