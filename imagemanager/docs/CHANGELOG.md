# Changelog

## v0.0.5

- Release bump: launcher (`status.artifacts` EQL) and Artifact CR fallback rows; publish workflow adds `edabuilder publish --force` for catalog republish safety.

## v0.0.4

- Launcher dashlet reads `ImageManagerConfig.status.artifacts` via EQL (`.cluster...imagemanagerconfigs.default.status.artifacts`); controller mirrors tracked uploads and synthesizes fallback rows from managed Artifact CRs when PVC metadata is missing.
- Dropped the unused `ImageManagerArtifact` CRD after confirming nested `status.artifacts` works with EDA EQL.
