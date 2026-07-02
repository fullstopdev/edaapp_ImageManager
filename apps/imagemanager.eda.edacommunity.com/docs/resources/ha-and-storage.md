# High availability and storage

Image Manager is designed as a **lab-friendly, single-controller** app. This page
documents the current deployment model, what happens on failure, and how to harden
storage for more serious use.

## Current deployment model

| Component | HA posture |
|-----------|------------|
| **Controller** | Single-replica `Deployment`, `Recreate` strategy, one pod |
| **PVC** | `ReadWriteOnce`, 20 GiB — holds all uploaded NOS bytes |
| **Node agent** | `DaemonSet` — re-resolves the in-cluster registry redirect every cycle |
| **Dashboard status** | Ephemeral state DB rows on a persistent gRPC stream (see changelog) |

The controller is the **durable origin** for eda-asvr: eda-asvr re-pulls from Image
Manager whenever its pod restarts. The PVC is therefore the critical asset, not the
controller pod itself.

## Self-healing after restarts (v0.0.20+)

On startup (and every 10 reconcile cycles) the controller **re-derives state** instead
of trusting cached upload tracking:

1. **Stale temp dirs** — removes abandoned `.incoming-*` / `.import-*` directories
   older than `STALE_WORK_DIR_SECONDS` (default 1 hour).
2. **Incomplete uploads** — reports dirs with bytes on the PVC but no `meta.json`
   (pod died mid-finalize). These need manual cleanup or re-upload.
3. **Missing Artifact CRs** — for every upload with valid `meta.json`, if expected
   Artifact CRs are gone, runs `repush_from_local` to recreate CRs from PVC bytes
   without re-downloading.

This mirrors the node-agent pattern: **re-derive from authoritative sources**, don't
trust in-memory or half-written state.

## PVC backup (recommended)

Because the PVC is the only durable copy of uploaded images:

- Schedule periodic snapshots or volume backups of `imagemanager-data` in
  `eda-system`.
- After restore, restart the controller pod — startup reconcile republishes Artifact
  CRs from restored `meta.json` files.
- Test restore in a lab before relying on it in production.

Example (cluster-dependent — adjust for your storage class / backup tool):

```bash
# Velero example (illustrative)
velero backup create imagemanager-pvc --include-namespaces eda-system \
  --selector eda.nokia.com/app=eda-imagemanager
```

## External artifact origin (advanced)

For environments that already have a central artifact store, you can point Artifact
CRs at an **external HTTPS pull URL** instead of this app's in-cluster file server:

1. Open **Settings → File-pull base URL** and set e.g.
   `https://artifacts.example.com/imagemanager`.
2. Upload/import as usual — bytes still land on the PVC for the web UI and for
   replace/repush, but new Artifact CRs reference the external base URL.
3. Ensure eda-asvr can reach that URL and trust its TLS (trust-bundle ConfigMaps as
   today).

A future release may add a first-class **S3-compatible backend** so the PVC becomes
a cache rather than the sole copy. Until then, `filePullBaseUrl` is the supported
hook for external origins.

## Why not multi-replica today?

- **RWO PVC** — only one pod can mount the upload volume at a time.
- **Recreate strategy** — avoids two pods fighting over the same PVC during upgrades.
- **Upload atomicity** — large streaming uploads assume a single writer.

Running multiple replicas would require either ReadWriteMany storage with distributed
locking, or moving bytes to an external object store. That is out of scope for the
current lab-focused release.

## Operational checklist

- [ ] PVC backup schedule in place
- [ ] Monitor dashboard **Reconcile** strip for incomplete dirs or repush failures
- [ ] Keep controller at `replicas: 1` unless you have RWX + external storage
- [ ] Use `filePullBaseUrl` when eda-asvr should pull from org artifact store
- [ ] Node agent enabled for SR-SIM (`nodeAgentEnabled` in app settings)
