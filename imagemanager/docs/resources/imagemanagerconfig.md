---
resource_name: ImageManagerConfig
resource_name_plural: imagemanagerconfigs
resource_name_plural_title: Image Manager Configs
resource_name_acronym: IM
crd_path: docs/imagemanager.eda.edacommunity.com/crds/imagemanager.eda.edacommunity.com_imagemanagerconfigs.yaml
icon: auto-crd
---

# Image Manager Config

Cluster-wide settings and live status for EDA Image Manager. The controller
auto-creates a single instance named `default` on first boot.

## What to edit (spec)

| Field | Default | Effect |
|-------|---------|--------|
| `defaultArtifactNamespace` | `eda` | Pre-selects this namespace in the upload UI dropdown |
| `defaultRepo` | `images` | Default artifact repo for SR Linux uploads |
| `maxUploadMiB` | `4096` | Rejects browser and API uploads larger than this |
| `filePullBaseUrl` | _(auto)_ | Advanced: override the URL eda-asvr uses to pull files |

## What to read (status)

`status` is written by the controller each reconcile cycle: overall `health`,
PVC `uploadsStored` / `bytesStored`, and a denormalized `artifacts` list with
each Artifact's live `downloadStatus` from eda-asvr.

## Examples

/// tab | YAML

```yaml
-{{ include_snippet(resource_name) }}-
```

///

/// tab | `kubectl`

```bash
cat << 'EOF' | kubectl apply -f -
-{{ include_snippet(resource_name) }}-
EOF
```

///

## Custom Resource Definition

To browse the Custom Resource Definition go to [crd.eda.dev](https://crd.eda.dev/-{{ resource_name_plural }}-.-{{ app_group }}-/-{{ app_api_version }}-).

-{{ crd_viewer(crd_path, collapsed=False) }}-
