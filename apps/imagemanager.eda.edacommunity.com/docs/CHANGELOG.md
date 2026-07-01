# Changelog

## v0.0.1

Initial public release (Image Manager for EDA):

- Web UI to upload SR Linux, SR OS hardware, and SR-SIM zips; automatic type detection, md5, and YANG schema profile resolution (schema-profiles or on-the-fly from `nokia/7x50_YangModels`).
- Controller file server, Artifact CR management, PVC-backed storage, and NodeProfile snippet helpers.
- EDA launcher dashboard with cluster-scoped `ImageManagerArtifact` CRs (flat status column bindings for EDA EQL).
- Offline air-gap bundle attached to each GitHub Release under `apps/imagemanager.eda.edacommunity.com/<version>`.
