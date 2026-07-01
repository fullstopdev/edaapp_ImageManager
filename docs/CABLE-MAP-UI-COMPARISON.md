# Cable Map vs Image Manager — EDA view / UI comparison

Research date: 2026-07-01. Sources: `eda-labs/catalog` (`apps/cable-map.eda.labs`),
OCI image `ghcr.io/eda-labs/cable-map:v0.2.2` (view + CR blobs extracted via `crane`),
`nokia-eda/docs` release-26.4, and this repo’s `imagemanager/` tree.

## Executive summary

**Cable Map does not use `type: "iframe"`.** Its view JSON is a full EDA dashboard
(`screens` → `flexRow` → `dashletDataView`) with an **external** navigation target
pointing at `/core/httpproxy/v1/cable-map/`. The SPA opens when the user clicks
**View** (new tab by default), not embedded in the nav panel.

**Image Manager uses a minimal 6-line JSON** with `"type": "iframe"` and
`"sameOrigin": true`, which asks the EDA shell to **embed** the HttpProxy URL in an
iframe inside the nav content area. That pattern is **not** what cable-map uses and
is **not documented** in nokia-eda/docs. It may be accepted by the store but is
the highest-risk difference for a blank/black nav panel.

A blank/black panel with the EDA chrome visible (“Image Manager”, Live) is therefore
more likely caused by **iframe embed + SPA boot/auth** than by HttpProxy wiring alone.
v26.4.2-30 addressed SPA-side causes (auth scrim, boot shell, SSO timeout). Aligning
the view JSON with cable-map’s launcher-dashboard pattern is the structural fix if
iframe embed remains unreliable.

---

## 1. Manifest `view` component

### Cable Map (`apps/cable-map.eda.labs/manifest.yaml`)

```yaml
    - view:
        path: cable_map/ui/cable-map-dashboard.json
        ui:
          category: Topology
          icon: Topology
          name: Cable Map
```

- Single view entry under **Topology**.
- Runtime shipped as embedded container dependency (`image/cable-map`).
- Docs: `cable_map/docs/README.md`, `index.md`, `CHANGELOG.md`.

### Image Manager (`imagemanager/manifest.yaml`)

```yaml
    - view:
        path: imagemanager/ui/imagemanager-dashboard.json
        ui:
          category: Image Manager
          name: Image Manager
          icon: Import
```

- Same manifest shape (`view.path` + `ui.category/name/icon`).
- **Difference:** custom top-level nav category vs cable-map under Topology.
- Also registers CRDs, Deployment, Service, HttpProxy, PVC, DaemonSet (cable-map
  has Deployment/Service/HttpProxy/access only).

---

## 2. Dashboard / view JSON schema

### Cable Map — actual `cable-map-dashboard.json` (from OCI v0.2.2)

Top-level keys: `uuid`, `name`, `version`, `displayName`, `description`,
`showNavigationToolbar`, `lastChanged`, `screens[]`.

Each screen: `screenType: "dashboard"`, `partOfNav`, `startScreen`, nested
`components[]` with:

| Layer | `type` | Role |
|-------|--------|------|
| Row | `flexRow` | Layout |
| Panel | `dashletDataView` | Launcher card + status table |
| Nav | `navigationTarget` | Opens SPA |

Navigation target (dashlet + row template):

```json
{
  "edaRoute": "external",
  "targetReference": "/core/httpproxy/v1/cable-map/",
  "useNewTab": true
}
```

Data source: EQL `get` on `.cluster.apps.cable-map.status` with columns
`service`, `open` (View link), `status`, `namespaces`, `nodes`, `links`, `lags`.

**No `iframe`, `sameOrigin`, or `url` top-level fields.**

### Image Manager — `imagemanager-dashboard.json` (current)

```json
{
  "type": "iframe",
  "title": "Image Manager",
  "description": "Upload vendor NOS images into EDA and create Artifacts for node bootstrap.",
  "url": "/core/httpproxy/v1/imagemanager/",
  "sameOrigin": true
}
```

**This is not the cable-map schema.** Nokia EDA docs (`development/apps/components.md`,
`user-guide/dashboards.md`) describe dashboards as flex layouts + dashlets; they
document **external** nav targets on dashlets, not a top-level `iframe` view type.
`stockLauncher` is documentation wording (“stock launcher card”), not a JSON `type`.

---

## 3. HttpProxy setup

| | Cable Map | Image Manager |
|---|-----------|---------------|
| **CR name** | `cable-map` | `imagemanager` |
| **Public path** | `/core/httpproxy/v1/cable-map/` | `/core/httpproxy/v1/imagemanager/` |
| **authType** | `atDestination` | `atDestination` |
| **rootUrl** | `http://cable-map.${EDA_BASE_NAMESPACE}.svc:8080/` | `https://eda-imagemanager.eda-system.svc:8443/` |
| **Backend TLS** | Plain HTTP on 8080 | HTTPS on 8443 (cert-manager CSI) |
| **Service** | `cable-map:8080` ClusterIP | `eda-imagemanager:8443` ClusterIP |

Both are internal ClusterIP services; neither installs NodePort or patches EDA UI.

**Verification (from cable-map docs, applies to both):**

```sh
curl -k -I https://<eda-origin>/core/httpproxy/v1/cable-map/
curl -k -I https://<eda-origin>/core/httpproxy/v1/imagemanager/
kubectl -n eda-system get httpproxy <name> -o yaml
```

---

## 4. Cable-map-specific controller / SPA patterns

From catalog docs + extracted manifests:

1. **Launcher, not iframe embed** — Nav shows dashboard card; SPA via HttpProxy on
   **View** click (`useNewTab: true`).
2. **SSO** — `keycloak-js` public client `auth`, identity proxy
   `/core/proxy/v1/identity`, silent SSO callback as same-origin asset (CSP
   `script-src 'self'`).
3. **Session exchange** — Browser token → HTTP-only session cookie; backend validates
   with confidential `eda` client + `keycloak-admin-secret` / `eda-api-ca` RBAC.
4. **UI shell without session** — `/` loads without cookie so silent SSO can run;
   `/api/*` returns 401 until session exists (same pattern as imagemanager
   `fileserver.py`).
5. **EDA ClusterRole `cable-map-viewer`** — `urlRules` for
   `/core/httpproxy/v1/cable-map/**`, `tableRules` for
   `.cluster.apps.cable-map.**`, plus read on topology CRs.
6. **App status EQL** — `.cluster.apps.cable-map.status` feeds the launcher table.

Image Manager already mirrors (2)–(4) in `auth.py`, `fileserver.py`, `webui.py`.
**Missing vs cable-map:** (5) EDA `ClusterRole` + `urlRules`, (6) app-level status
table for a launcher dashlet.

---

## 5. Differences that can cause blank/black iframe (imagemanager)

| # | Difference | Effect |
|---|------------|--------|
| 1 | **`type: iframe` embed** vs cable-map **external launcher** | EDA hosts empty/broken iframe if embed path or height/auth fails; cable-map never embeds SPA in nav. |
| 2 | **SPA auth scrim** (fixed v26.4.2-30) | Full-screen dark overlay matched EDA shell `#101824` → looked empty during SSO. |
| 3 | **No `urlRules` ClusterRole** | Non-admin users may lack HttpProxy permission; admins usually OK. |
| 4 | **No `.cluster.apps.*.status` EQL** | Cannot drop in cable-map launcher JSON verbatim; need ImageManagerConfig-based EQL or static card. |
| 5 | **HTTPS backend** | Unlikely alone if direct `/core/httpproxy/v1/imagemanager/` works; proxy terminates TLS to backend. |

Direct URL test isolates (1) vs (2): if
`https://<eda>/core/httpproxy/v1/imagemanager/` works in a tab but nav is black,
the problem is **view embed**, not HttpProxy/controller.

---

## 6. Recommendations to align with cable-map

### A. Replace iframe view JSON (preferred structural alignment)

Rewrite `imagemanager/ui/imagemanager-dashboard.json` as a cable-map-style dashboard:

- `screens[0].components[0].type = "flexRow"`
- Child `dashletDataView` with subtitle like cable-map
- `navigationTarget.edaRoute = "external"`
- `targetReference = "/core/httpproxy/v1/imagemanager/"`
- `useNewTab = true` (match cable-map) or `false` if same-tab SPA is desired

Data API options:

- **Option 1:** Expose `.cluster.apps.imagemanager.status` (cable-map parity) from the
  controller and query it like cable-map.
- **Option 2:** Query `ImageManagerConfig/default` status (artifacts, health) via EQL
  on the imagemanager CRD — path must be validated on a live cluster.
- **Option 3:** Minimal static dashlet (no live rows) with only the View nav target.

Use new `uuid` values (generate v4); bump `version` string.

### B. Add EDA ClusterRole (access parity)

Add `imagemanager-viewer` `ClusterRole` (core.eda.nokia.com/v1) with:

```yaml
urlRules:
  - path: /core/httpproxy/v1/imagemanager
    permissions: read
  - path: /core/httpproxy/v1/imagemanager/**
    permissions: read
tableRules:
  - path: .cluster.apps.imagemanager.**   # if status table added
    permissions: read
```

Wire `allowedRoles` appsetting default to `imagemanager-viewer,system-administrator`.

### C. Keep iframe embed only if required

If product intent is **inline** SPA (not new tab), `type: iframe` may be valid on
some EDA builds — confirm against docs.eda.dev or Nokia support. Ensure:

- `url` is relative, trailing slash: `/core/httpproxy/v1/imagemanager/`
- `sameOrigin: true`
- SPA: no full-screen scrim, visible `#boot-shell`, SSO timeout (v26.4.2-30)
- Iframe `min-height` / `eda-embedded` CSS so content is not zero-height

### D. Publish checklist

1. Bump `spec.image` + controller tag.
2. `make imagemanager-generate` (Go 1.26.2+).
3. `edabuilder build-push` + catalog publish.
4. Reinstall/upgrade app in EDA; hard-refresh browser.
5. Verify nav card **and** direct HttpProxy URL.

---

## 7. Exact fix if `imagemanager-dashboard.json` format is wrong

**Yes — format mismatch is confirmed.** The file should **not** be the minimal
`iframe` object if following cable-map. Minimum change direction:

- **Delete** top-level `"type": "iframe"`, `"url"`, `"sameOrigin"`.
- **Adopt** full dashboard document per section 2 (cable-map OCI extract).
- Point all `navigationTarget.targetReference` values at
  `/core/httpproxy/v1/imagemanager/`.

Reference template: `/tmp/cable-extract/cable-map-dashboard.json` from
`ghcr.io/eda-labs/cable-map:v0.2.2` view layer blob
`sha256:4444d9bc2d02c9ded367cc189e014cb2dc3bb5b9e0fa4db4a4badb5a08213491`.

---

## Appendix: OCI layout

Both apps publish as `application/vnd.nokia.eda.apps.root.v1` with component manifests:

- `application/vnd.nokia.eda.apps.component.view.v1` — dashboard JSON layer
- `application/vnd.nokia.eda.apps.component.cr.v1` — K8s/EDA CR YAML layers

Cable-map view layer is raw JSON (not tar). Image Manager view layer is 213 bytes
(the iframe JSON).
