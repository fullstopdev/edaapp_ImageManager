"""
Embedded HTTPS server (port 8443). Runs as a daemon thread.

Serves three audiences on one port:
  * the browser, via the EDA HttpProxy (path prefixed /core/httpproxy/v1/imagemanager)
      GET  /                 the upload web UI
      GET  /healthz          liveness/readiness (also used by kubelet probes)
      GET  /api/config       defaults for the UI form
      GET  /api/settings     ImageManagerConfig spec + status (Settings tab)
      PUT  /api/settings     update ImageManagerConfig/default
      GET  /api/namespaces   namespace names for the UI (best-effort)
      GET  /api/artifacts    tracked uploads + live Artifact download status
      GET  /api/imports      ImageImport CR list (Status tab)
      POST /api/upload       raw-body file upload -> store on PVC -> create Artifact
      POST /api/url-import   create ImageImport CR from URL (URL Import tab)
  * eda-asvr, connecting directly to the Service to PULL an uploaded file:
      GET/HEAD /files/<uploadId>/<filename>[.md5]
TLS: serving cert from the cert-manager CSI mount (issuer eda-internal-issuer),
which eda-asvr trusts via the internal CA.
"""

import html
import json
import logging
import os
import re
from pathlib import Path
import shutil
import ssl
import tempfile
import threading
import time
import urllib.error
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

import artifact
import auth
import import_common
import k8s
import schemaprofile
import uploads
import webui

logger = logging.getLogger("fileserver")


def set_storage_reconcile(report):
    _storage_reconcile[0] = dict(report or {})


def get_storage_reconcile():
    return dict(_storage_reconcile[0] or {})


def _sync_app_status_now():
    """Push launcher rows immediately after upload/delete (don't wait for reconcile)."""
    try:
        import app_status
        app_status.sync_app_status_rows(build_tracked_list())
    except Exception as e:  # noqa: BLE001
        logger.debug("immediate app status sync failed: %s", e)
    # Also wake the sync loop: it re-checks shortly after, catching anything
    # still settling at the instant of the inline publish (e.g. a CR whose
    # finalizer hadn't run yet when we listed).
    kick = SYNC_KICK[0]
    if kick:
        try:
            kick()
        except Exception:  # noqa: BLE001
            pass


UPLOAD_DIR = "/data/uploads"
HEALTHZ_FILE = os.path.join(UPLOAD_DIR, ".healthz.json")
PROXY_PREFIX = "/core/httpproxy/v1/imagemanager"
TLS_DIR = "/var/run/eda/tls/serving"
_SERVE_CHUNK = 256 * 1024

IM_CRD_GROUP = "imagemanager.eda.edacommunity.com"
IM_CRD_VERSION = "v1alpha1"
IM_CONFIG_PLURAL = "imagemanagerconfigs"
IM_IMPORT_PLURAL = "imageimports"
IM_CONFIG_NAME = "default"

# Set by main: zero-arg callable that kicks the ImageImport reconcile
# immediately (so a URL import starts within seconds, not at the next tick).
IMPORT_KICK = [None]
# Set by main: zero-arg callable that wakes the dashboard status sync loop.
SYNC_KICK = [None]
# Last storage reconcile snapshot (startup + periodic re-derive).
_storage_reconcile = [{}]
# Set by main at startup; surfaced in /api/config for the UI version chip.
APP_VERSION = [""]

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
APP_LOGO_PNG = (_ASSETS_DIR / "nokia-logo.png").read_bytes()
APP_N_LOGO_PNG = (_ASSETS_DIR / "nokia-n.png").read_bytes()

# Shared, set by main each reconcile cycle (dict assignment is atomic in CPython).
CONFIG = {
    "defaultArtifactNamespace": "eda",
    "defaultRepo": "images",
    "maxUploadMiB": 4096,
    "filePullBaseUrl": "",
}
POD_NAMESPACE = os.environ.get("POD_NAMESPACE", "eda-system")
SERVICE_NAME = "eda-imagemanager"
# License ConfigMaps live where eda-cx resolves them (and where EDA keeps its own):
# the EDA system namespace, which is also where this app runs. A NodeProfile in a
# user namespace references the ConfigMap by name; the consumer reads it here.
LICENSE_NS = POD_NAMESPACE

_server = None
_server_lock = threading.Lock()
_tracked_cache = {"at": 0.0, "data": None}
_tracked_lock = threading.Lock()
_TRACKED_TTL = 3  # seconds; UI polls at 4s when active, fast status loop at 5s

# OCI distribution (registry v2) path patterns. `name` may contain '/'.
_V2_MANIFEST_RE = re.compile(r"^/v2/(.+)/manifests/(.+)$")
_V2_BLOB_RE = re.compile(r"^/v2/(.+)/blobs/(sha256:[0-9a-f]{64})$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def sim_registry_host():
    """The registry host that the node's containerd reaches this app at (the
    Service FQDN, which is also the serving cert's SAN). A one-time Talos
    machine.registries mirror maps this host to the in-cluster Service. Used as
    the host in a SR-SIM NodeProfile's containerImage."""
    return f"{SERVICE_NAME}.{POD_NAMESPACE}.svc"

# Material-styled standalone message page (sign-out / access-denied). Mirrors the
# EDA palette + the saved Light/Dark preference used by the main UI.
_MSG_PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>{title}</title>
<script>try{{document.documentElement.setAttribute("data-theme",localStorage.getItem("imagemanager-theme")||"light");}}catch(e){{}}</script>
<style>
 :root{{--bg:#f7f9fd;--panel:#fff;--fg:#2b2b2b;--muted:#687282;--accent:#005aff;--accent2:#0a44ad;--line:#d9dee7;--elev:0 11px 18px rgba(20,30,50,.18),0 22px 44px rgba(20,30,50,.22);}}
 html[data-theme=dark]{{--bg:#101824;--panel:#1a222e;--fg:#e6edf3;--muted:#8b98a6;--accent:#4d8dff;--accent2:#6aa4ff;--line:#2c3644;--elev:0 22px 48px rgba(0,0,0,.7);}}
 *{{box-sizing:border-box}}
 body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--fg);font:14px/1.55 "Nokia Pure Text","Inter","Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:24px}}
 .card{{background:var(--panel);border-radius:16px;box-shadow:var(--elev);padding:30px 32px;max-width:460px;width:100%}}
 .mark{{width:18px;height:18px;border-radius:5px;background:var(--accent);box-shadow:0 0 0 4px color-mix(in srgb,var(--accent) 20%,transparent);display:inline-block;vertical-align:-2px;margin-right:9px}}
 h2{{margin:0 0 12px;font-size:19px;font-weight:600}}
 p{{margin:8px 0;color:var(--fg)}} p.muted{{color:var(--muted);font-size:13px}}
 .imbtn{{display:inline-block;margin-top:16px;background:var(--accent);color:#fff;text-decoration:none;border-radius:8px;padding:10px 20px;font-weight:600;font-size:13.5px}}
 .imbtn:hover{{background:var(--accent2)}}
 .imbtn.ghost{{background:transparent;color:var(--accent);border:1px solid var(--line)}}
 .imbtn.ghost:hover{{background:color-mix(in srgb,var(--accent) 8%,transparent)}}
</style></head><body><div class="card"><h2><span class="mark"></span>{heading}</h2>{body}{action}</div></body></html>"""


def set_config(cfg):
    global CONFIG
    CONFIG = cfg


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet; we log meaningful events ourselves

    # --------------------------- helpers ---------------------------

    def _route(self):
        """Return (path, query_dict) with query stripped and proxy prefix removed."""
        parts = urlsplit(self.path)
        path = parts.path
        if path.startswith(PROXY_PREFIX):
            path = path[len(PROXY_PREFIX):] or "/"
        if len(path) > 1:
            path = path.rstrip("/")
        return path or "/", parse_qs(parts.query)

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text, code=200, ctype="text/plain; charset=utf-8"):
        body = text.encode("utf-8") if isinstance(text, str) else text
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --------------------------- auth (EDA SSO) ---------------------------

    def _cookie(self, name):
        raw = self.headers.get("Cookie")
        if not raw:
            return ""
        c = SimpleCookie()
        try:
            c.load(raw)
        except Exception:
            return ""
        m = c.get(name)
        return m.value if m else ""

    def _authed_user(self):
        """Username if the request carries a valid session, else None.
        With auth disabled (local dev), returns a placeholder user."""
        if not auth.enabled():
            return "local"
        return auth.verify_session(self._cookie(auth.SESSION_COOKIE))

    def _set_cookie(self, name, value, max_age):
        parts = [f"{name}={value}", f"Path={auth.APP_PROXY_PREFIX}",
                 "HttpOnly", "Secure", "SameSite=Lax"]
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        self.send_header("Set-Cookie", "; ".join(parts))

    def _redirect(self, location, cookies=None):
        self.send_response(302)
        for (n, v, a) in (cookies or []):
            self._set_cookie(n, v, a)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _redirect_to_login(self):
        state = auth.new_state()
        try:
            url = auth.authorize_url(self.headers, state)
        except Exception as e:
            logger.error("Cannot build authorize URL: %s", e)
            self._send_text("Sign-in is unavailable: cannot reach EDA Keycloak.", 503)
            return
        self._redirect(url, cookies=[(auth.STATE_COOKIE, state, 600)])

    def _handle_oauth_session(self):
        """Exchange a keycloak-js access token for an HTTP-only session cookie."""
        auth_hdr = self.headers.get("Authorization", "")
        token = ""
        if auth_hdr.lower().startswith("bearer "):
            token = auth_hdr[7:].strip()
        if not token:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(n) if n else b""
            try:
                token = (json.loads(body.decode("utf-8")) if body else {}).get("token", "")
            except Exception:
                token = ""
        user, roles = auth.jwt_identity(token)
        if not user:
            self._send_json({"ok": False, "error": "invalid or expired token"}, 401)
            return
        if not auth.is_allowed(roles):
            self._send_json({
                "ok": False,
                "error": "forbidden",
                "user": user,
                "allowedRoles": auth.allowed_roles(),
            }, 403)
            return
        tok_exp = auth.jwt_exp(token)
        self.send_response(200)
        self._set_cookie(auth.SESSION_COOKIE,
                         auth.make_session(user, token_exp=tok_exp),
                         auth.session_cookie_max_age(tok_exp))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "user": user}).encode("utf-8"))

    def _handle_oauth_session_logout(self):
        """Clear the local session cookie (browser-initiated SSO loss)."""
        self.send_response(200)
        self._set_cookie(auth.SESSION_COOKIE, "", 0)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))

    def _handle_oauth_callback(self, q):
        code = (q.get("code") or [None])[0]
        state = (q.get("state") or [None])[0]
        expected = self._cookie(auth.STATE_COOKIE)
        if not code or not state or not expected or state != expected:
            self._send_text("Sign-in failed (invalid state). Please retry.", 400)
            return
        try:
            tok = auth.exchange_code(code, self.headers)
        except Exception as e:
            logger.error("OIDC code exchange failed: %s", e)
            self._send_text("Sign-in failed: could not complete authentication.", 502)
            return
        user, roles = auth.token_identity(tok)
        if not user:
            self._send_text("Sign-in failed: invalid token.", 502)
            return
        if not auth.is_allowed(roles):
            logger.info("Access denied: %s lacks an allowed role (have=%s need-any-of=%s)",
                        user, sorted(roles), auth.allowed_roles())
            self._deny_page(user)
            return
        logger.info("Sign-in OK: %s", user)
        access = tok.get("access_token", "")
        tok_exp = auth.jwt_exp(access)
        self._redirect(auth.APP_PROXY_PREFIX + "/", cookies=[
            (auth.SESSION_COOKIE,
             auth.make_session(user, token_exp=tok_exp),
             auth.session_cookie_max_age(tok_exp)),
            (auth.STATE_COOKIE, "", 0),
        ])

    def _handle_logout(self):
        """Clear local session and end the EDA Keycloak session (RP-initiated logout)."""
        post = auth.external_base(self.headers) + auth.APP_PROXY_PREFIX + "/"
        try:
            url = auth.end_session_url(self.headers, post)
        except Exception as e:
            logger.warning("Cannot build end_session URL: %s", e)
            url = auth.APP_PROXY_PREFIX + "/"
        self._redirect(url, cookies=[(auth.SESSION_COOKIE, "", 0)])

    def _deny_page(self, user):
        roles = ", ".join(auth.allowed_roles())
        link = auth.APP_PROXY_PREFIX + "/oauth/logout"
        self._send_text(
            _MSG_PAGE.format(
                title="Access denied",
                heading="Access denied",
                body=(f"<p>You're signed in to EDA as <b>{html.escape(user)}</b>, but Image "
                      f"Manager is restricted to users with the role: "
                      f"<b>{html.escape(roles)}</b>.</p>"
                      f"<p class='muted'>Ask an administrator for the role.</p>"),
                action=f"<a class='imbtn ghost' href='{link}'>Sign out</a>",
            ),
            403, ctype="text/html; charset=utf-8")

    # --------------------------- GET / HEAD ---------------------------

    def do_GET(self):
        path, q = self._route()
        try:
            # Machine endpoints — never gated (kubelet probes; eda-asvr file pulls).
            if path == "/healthz":
                self._serve_healthz()
                return
            if path.startswith("/files/"):
                self._serve_file(path[len("/files/"):], head_only=False)
                return
            # OCI registry (read-only) — the node's containerd pulls SR-SIM sim
            # images from here. Machine traffic (no OIDC); auth is by network reach
            # to the in-cluster Service, like /files/.
            if path == "/v2" or path.startswith("/v2/"):
                self._serve_registry_v2(path, head_only=False)
                return
            # OIDC endpoints.
            if path == "/oauth/callback":
                self._handle_oauth_callback(q)
                return
            if path == "/oauth/logout":
                self._handle_logout()
                return
            if path == "/oauth/login":
                self._redirect_to_login()
                return
            if path == "/oauth/silent-sso.html":
                self._send_text(webui.SILENT_SSO_HTML, ctype="text/html; charset=utf-8")
                return
            if path == "/assets/nokia-logo.png":
                self._send_text(APP_LOGO_PNG, ctype="image/png")
                return
            if path == "/assets/nokia-n.png":
                self._send_text(APP_N_LOGO_PNG, ctype="image/png")
                return
            # UI shell loads without a session so keycloak-js can perform silent SSO
            # inside the EDA iframe (cable-map.eda.labs pattern). Data APIs stay gated.
            if path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                body = webui.INDEX_HTML.encode("utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if auth.enabled() and not self._authed_user():
                if path.startswith("/api/"):
                    self._send_json({"ok": False, "error": "not authenticated"}, 401)
                else:
                    self.send_error(404, "Not Found")
                return
            if path == "/api/config":
                self._serve_config()
            elif path == "/api/settings":
                self._serve_settings()
            elif path == "/api/namespaces":
                self._serve_namespaces()
            elif path == "/api/artifacts":
                self._serve_artifacts()
            elif path == "/api/imports":
                self._serve_imports()
            else:
                self.send_error(404, "Not Found")
        except BrokenPipeError:
            pass
        except Exception as e:
            logger.error("GET %s failed: %s", self.path, e)
            try:
                self.send_error(500, "Internal Server Error")
            except Exception:
                pass

    def do_HEAD(self):
        path, _ = self._route()
        try:
            if path.startswith("/files/"):
                self._serve_file(path[len("/files/"):], head_only=True)
            elif path == "/v2" or path.startswith("/v2/"):
                self._serve_registry_v2(path, head_only=True)
            elif path in ("/", "/healthz"):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
            else:
                self.send_error(404, "Not Found")
        except Exception:
            pass

    def _serve_healthz(self):
        try:
            with open(HEALTHZ_FILE) as f:
                self._send_text(f.read(), ctype="application/json")
        except FileNotFoundError:
            self._send_text('{"status":"starting","last_reconcile":null}',
                            ctype="application/json")

    def _serve_config(self):
        c = CONFIG
        self._send_json({
            "defaultArtifactNamespace": c.get("defaultArtifactNamespace", "eda"),
            "defaultRepo": c.get("defaultRepo", "images"),
            "maxUploadMiB": c.get("maxUploadMiB", 4096),
            "user": self._authed_user() or "",
            "version": APP_VERSION[0],
        })

    def _serve_settings(self):
        """Read ImageManagerConfig/default spec + live status for the Settings tab."""
        spec = dict(CONFIG)
        health, message, version = "", "", ""
        try:
            cr = k8s.read_cr(IM_CRD_GROUP, IM_CRD_VERSION, IM_CONFIG_PLURAL, IM_CONFIG_NAME)
            if cr:
                spec.update({k: v for k, v in (cr.get("spec") or {}).items()
                             if v not in (None, "")})
                st = cr.get("status") or {}
                health = st.get("health") or ""
                message = st.get("message") or ""
                version = st.get("version") or ""
        except Exception as e:
            logger.warning("settings read failed: %s", e)
        self._send_json({
            "defaultArtifactNamespace": spec.get("defaultArtifactNamespace", "eda"),
            "defaultRepo": spec.get("defaultRepo", "images"),
            "maxUploadMiB": int(spec.get("maxUploadMiB", 4096)),
            "filePullBaseUrl": spec.get("filePullBaseUrl") or "",
            "health": health,
            "message": message,
            "version": version,
        })

    def _apply_settings(self, body):
        """Merge validated settings into ImageManagerConfig/default spec."""
        cr = k8s.read_cr(IM_CRD_GROUP, IM_CRD_VERSION, IM_CONFIG_PLURAL, IM_CONFIG_NAME)
        if not cr:
            self._send_json({"ok": False, "error": "ImageManagerConfig/default not found"}, 404)
            return
        spec = dict(cr.get("spec") or {})
        if "defaultArtifactNamespace" in body:
            ns = (body.get("defaultArtifactNamespace") or "").strip()
            if not ns:
                self._send_json({"ok": False, "error": "defaultArtifactNamespace is required"}, 400)
                return
            spec["defaultArtifactNamespace"] = ns
        if "defaultRepo" in body:
            repo = (body.get("defaultRepo") or "").strip()
            if not repo:
                self._send_json({"ok": False, "error": "defaultRepo is required"}, 400)
                return
            spec["defaultRepo"] = repo
        if "maxUploadMiB" in body:
            try:
                mib = int(body.get("maxUploadMiB"))
            except (TypeError, ValueError):
                self._send_json({"ok": False, "error": "maxUploadMiB must be an integer"}, 400)
                return
            if mib < 1 or mib > 65536:
                self._send_json({"ok": False,
                                 "error": "maxUploadMiB must be between 1 and 65536"}, 400)
                return
            spec["maxUploadMiB"] = mib
        if "filePullBaseUrl" in body:
            spec["filePullBaseUrl"] = (body.get("filePullBaseUrl") or "").strip()
        cr["spec"] = spec
        try:
            k8s.update_cr(IM_CRD_GROUP, IM_CRD_VERSION, IM_CONFIG_PLURAL, IM_CONFIG_NAME, cr)
        except Exception as e:
            logger.error("settings update failed: %s", e)
            self._send_json({"ok": False, "error": str(e)}, 502)
            return
        merged = dict(CONFIG)
        merged.update({k: v for k, v in spec.items() if v not in (None, "")})
        merged["maxUploadMiB"] = max(1, min(65536, int(merged.get("maxUploadMiB", 4096))))
        set_config(merged)
        self._send_json({"ok": True, "settings": {
            "defaultArtifactNamespace": merged.get("defaultArtifactNamespace", "eda"),
            "defaultRepo": merged.get("defaultRepo", "images"),
            "maxUploadMiB": merged.get("maxUploadMiB", 4096),
            "filePullBaseUrl": merged.get("filePullBaseUrl") or "",
        }})

    def _serve_imports(self):
        """List ImageImport CRs for the Status tab."""
        out = []
        try:
            for cr in k8s.list_cr_all_namespaces(IM_CRD_GROUP, IM_CRD_VERSION, IM_IMPORT_PLURAL):
                md = cr.get("metadata") or {}
                spec = cr.get("spec") or {}
                st = cr.get("status") or {}
                out.append({
                    "name": md.get("name", ""),
                    "namespace": md.get("namespace", ""),
                    "sourceUrl": spec.get("sourceUrl", ""),
                    "specName": spec.get("name", ""),
                    "phase": st.get("phase") or "Pending",
                    "message": st.get("message", ""),
                    "detectedNos": st.get("detectedNos", ""),
                    "sizeBytes": st.get("sizeBytes"),
                    "startTime": st.get("startTime", ""),
                    "completionTime": st.get("completionTime", ""),
                })
        except Exception as e:
            logger.warning("imports list failed: %s", e)
            self._send_json({"ok": False, "error": str(e), "imports": []}, 502)
            return
        out.sort(key=lambda r: r.get("startTime") or r.get("name") or "", reverse=True)
        self._send_json({"imports": out})

    def _serve_namespaces(self):
        import k8s
        names = []
        try:
            # Suggest only EDA *user* namespaces (labelled eda.nokia.com/source,
            # e.g. eda/demo) — not infrastructure namespaces (eda-system, kube-*,
            # cert-manager, rook-ceph, vcluster-*, ...). The field is still free
            # text, so a user can type any namespace manually.
            q = urlencode({"labelSelector": "eda.nokia.com/source"})
            obj = k8s._request("GET", "/api/v1/namespaces?" + q)  # noqa: SLF001
            names = sorted(
                ns["metadata"]["name"] for ns in (obj or {}).get("items", [])
            )
        except Exception as e:
            logger.info("namespace list unavailable (RBAC?): %s", e)
        self._send_json({"namespaces": names})

    def _serve_artifacts(self):
        snap = get_storage_reconcile()
        self._send_json({
            "artifacts": build_tracked_list(),
            "storage": uploads.disk_usage(),
            "system": {
                "version": APP_VERSION[0],
                "deploymentMode": "single-replica",
                "storageBackend": "pvc",
                "filePullBaseUrl": CONFIG.get("filePullBaseUrl") or "",
                "workDirsActive": uploads.count_work_dirs(),
                "reconcile": snap,
            },
        })

    def _serve_file(self, rest, head_only):
        # rest = "<uploadId>/<filename>" (filename may end with .md5)
        rest = unquote(rest)
        comps = rest.split("/")
        if len(comps) != 2 or any(c in ("", ".", "..") for c in comps):
            self.send_error(400, "Bad path")
            return
        upload_id, filename = comps
        if "/" in filename or "\\" in filename:
            self.send_error(400, "Bad path")
            return
        base = os.path.realpath(os.path.join(UPLOAD_DIR, upload_id))
        full = os.path.realpath(os.path.join(base, filename))
        if not full.startswith(os.path.realpath(UPLOAD_DIR) + os.sep):
            self.send_error(403, "Forbidden")
            return
        if not os.path.isfile(full):
            self.send_error(404, "Not Found")
            return
        size = os.path.getsize(full)
        ctype = "text/plain; charset=utf-8" if filename.endswith(".md5") \
            else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "none")
        self.end_headers()
        if head_only:
            return
        with open(full, "rb") as f:
            shutil.copyfileobj(f, self.wfile, _SERVE_CHUNK)

    # --------------------------- OCI registry (read-only v2) ---------------------------

    def _v2_404(self, msg="not found"):
        body = json.dumps({"errors": [{"code": "NOT_FOUND", "message": msg}]}).encode()
        self.send_response(404)
        self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_registry_v2(self, path, head_only):
        """Minimal pull-only OCI distribution endpoint backed by the OCI layouts
        unpacked under /data/uploads/<name>/. Implements GET/HEAD /v2/ (version
        check), /v2/<name>/manifests/<ref> and /v2/<name>/blobs/<digest>."""
        if path in ("/v2", "/v2/"):
            body = b"{}"
            self.send_response(200)
            self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            return
        m = _V2_MANIFEST_RE.match(path)
        if m:
            self._serve_oci_manifest(unquote(m.group(1)), unquote(m.group(2)), head_only)
            return
        b = _V2_BLOB_RE.match(path)
        if b:
            self._serve_oci_blob(unquote(b.group(1)), b.group(2), head_only)
            return
        self._v2_404("unsupported registry path")

    def _serve_oci_manifest(self, name, ref, head_only):
        meta, blobs_dir = uploads.srsim_meta(name)
        if not meta:
            self._v2_404("repository %s not found" % name)
            return
        manifest_digest = meta.get("manifestDigest") or ""
        media = meta.get("manifestMediaType") or "application/vnd.oci.image.manifest.v1+json"
        if ref == (meta.get("imageTag") or ""):
            digest = manifest_digest
        elif ref.startswith("sha256:"):
            digest = ref
        else:
            self._v2_404("manifest %s unknown" % ref)
            return
        h = digest.split(":", 1)[1] if ":" in digest else ""
        if not _SHA256_HEX.match(h):
            self._v2_404("bad manifest digest")
            return
        full = os.path.join(blobs_dir, h)
        if not os.path.isfile(full):
            self._v2_404("manifest blob missing")
            return
        size = os.path.getsize(full)
        self.send_response(200)
        self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
        self.send_header("Content-Type",
                         media if digest == manifest_digest else "application/octet-stream")
        self.send_header("Docker-Content-Digest", digest)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if head_only:
            return
        with open(full, "rb") as f:
            shutil.copyfileobj(f, self.wfile, _SERVE_CHUNK)

    def _serve_oci_blob(self, name, digest, head_only):
        meta, blobs_dir = uploads.srsim_meta(name)
        if not meta:
            self._v2_404("repository %s not found" % name)
            return
        h = digest.split(":", 1)[1]
        if not _SHA256_HEX.match(h):
            self._v2_404("bad blob digest")
            return
        full = os.path.join(blobs_dir, h)
        if not os.path.isfile(full):
            self._v2_404("blob unknown")
            return
        size = os.path.getsize(full)
        # Optional single-range request (containerd may resume large layer pulls).
        start, end, partial = 0, size - 1, False
        rng = self.headers.get("Range")
        if rng:
            mm = re.match(r"bytes=(\d+)-(\d*)$", rng.strip())
            if mm:
                start = int(mm.group(1))
                end = int(mm.group(2)) if mm.group(2) else size - 1
                if start <= end < size:
                    partial = True
                else:
                    self.send_response(416)
                    self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
        length = (end - start + 1) if partial else size
        self.send_response(206 if partial else 200)
        self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Docker-Content-Digest", digest)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if head_only:
            return
        with open(full, "rb") as f:
            if start:
                f.seek(start)
            remaining = length
            while remaining > 0:
                buf = f.read(min(_SERVE_CHUNK, remaining))
                if not buf:
                    break
                self.wfile.write(buf)
                remaining -= len(buf)

    # --------------------------- PUT ---------------------------

    def do_PUT(self):
        path, _ = self._route()
        try:
            if auth.enabled() and not self._authed_user():
                self._send_json({"ok": False, "error": "not authenticated"}, 401)
                return
            if path == "/api/settings":
                n = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(n) if n else b""
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                except Exception:
                    self._send_json({"ok": False, "error": "invalid JSON body"}, 400)
                    return
                self._apply_settings(body)
            else:
                self.send_error(405, "Method Not Allowed")
        except BrokenPipeError:
            pass
        except Exception as e:
            logger.error("PUT %s failed: %s", self.path, e)
            try:
                self._send_json({"ok": False, "error": str(e)}, 500)
            except Exception:
                pass

    # --------------------------- POST ---------------------------

    def do_POST(self):
        path, q = self._route()
        try:
            if path == "/oauth/session":
                self._handle_oauth_session()
                return
            if path == "/oauth/session/logout":
                self._handle_oauth_session_logout()
                return
            # All other POSTs are user actions — require a valid EDA session.
            if auth.enabled() and not self._authed_user():
                self._send_json({"ok": False, "error": "not authenticated"}, 401)
                return
            if path == "/api/upload":
                self._handle_upload(q)
            elif path == "/api/url-import":
                self._handle_url_import()
            elif path == "/api/license":
                self._handle_license(q)
            elif path == "/api/delete":
                self._handle_delete(q)
            else:
                self.send_error(405, "Method Not Allowed")
        except BrokenPipeError:
            pass
        except Exception as e:
            logger.error("POST %s failed: %s", self.path, e)
            try:
                self._send_json({"ok": False, "error": str(e)}, code=500)
            except Exception:
                pass

    def _handle_url_import(self):
        """Create an ImageImport CR (declarative URL import) from the unified UI."""
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(n) if n else b""
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            self._send_json({"ok": False, "error": "invalid JSON body"}, 400)
            return
        url = (body.get("url") or body.get("sourceUrl") or "").strip()
        namespace = (body.get("namespace") or "").strip()
        replace = body.get("replace") in (True, "true", "1", 1)
        if not url or not url.lower().startswith(("http://", "https://")):
            self._send_json({"ok": False, "error": "url must be an http(s) URL"}, 400)
            return
        if not namespace:
            self._send_json({"ok": False, "error": "namespace is required"}, 400)
            return
        name_hint = (body.get("name") or "").strip().lower()
        if not name_hint:
            name_hint = uploads.derive_name(
                os.path.basename(url.split("?")[0]) or "import.zip")
        upload_id = uploads.to_k8s_name(name_hint) if name_hint else ""
        if upload_id and not replace:
            conflict = import_common.check_conflict(upload_id, namespace, name_hint)
            if conflict:
                self._send_json(conflict, 409)
                return
        if replace and upload_id and import_common.image_exists_locally(upload_id):
            result = import_common.repush_from_local(upload_id, CONFIG)
            invalidate_tracked_cache()
            _sync_app_status_now()
            self._send_json(result, result.get("status", 200 if result.get("ok") else 400))
            return
        base_name = uploads.to_k8s_name(
            (body.get("name") or "").strip()
            or os.path.basename(url.split("?")[0]).replace(".zip", "")
            or "import"
        ) or "import"
        cr_name = base_name
        for attempt in range(5):
            if not k8s.read_namespaced_cr(
                    IM_CRD_GROUP, IM_CRD_VERSION, namespace, IM_IMPORT_PLURAL, cr_name):
                break
            cr_name = uploads.to_k8s_name(f"{base_name}-{int(time.time())}-{attempt}")
        spec = {
            "sourceUrl": url,
            "insecureSkipTLSVerify": bool(body.get("insecureSkipTLSVerify")),
        }
        name_override = (body.get("name") or "").strip()
        if name_override:
            spec["name"] = name_override.lower()
        repo = (body.get("repo") or "").strip()
        if repo:
            spec["repo"] = repo
        lic = (body.get("licenseKey") or "").strip()
        if lic:
            spec["licenseKey"] = lic
        cr_body = {
            "apiVersion": f"{IM_CRD_GROUP}/{IM_CRD_VERSION}",
            "kind": "ImageImport",
            "metadata": {"name": cr_name, "namespace": namespace},
            "spec": spec,
        }
        if replace:
            cr_body["metadata"]["annotations"] = {
                import_common.REPLACE_ANNOTATION: "true",
            }
        try:
            k8s.create_namespaced_cr(
                IM_CRD_GROUP, IM_CRD_VERSION, namespace, IM_IMPORT_PLURAL, cr_body)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            self._send_json({"ok": False,
                             "error": f"create ImageImport failed (HTTP {e.code}): {detail}"},
                            502)
            return
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 502)
            return
        logger.info("URL import requested: %s/%s -> %s", namespace, cr_name, url)
        kick = IMPORT_KICK[0]
        if kick:
            try:
                kick()
            except Exception as e:  # noqa: BLE001 - reconcile tick still picks it up
                logger.debug("import kick failed: %s", e)
        self._send_json({"ok": True, "name": cr_name, "namespace": namespace})

    def _handle_license(self, q):
        """Attach a NOS license key to an already-uploaded image. The request body
        is the raw license file (a small text key file); we create/replace a
        ConfigMap (license.key) in eda-system that the image's NodeProfile
        references, and record it on the image's meta.json. Additive: never touches
        the image's own Artifacts. The image NOS comes from meta; a detected
        NOS-mismatch is surfaced as a non-blocking warning."""
        def one(name, default=None):
            v = q.get(name, [default])
            return v[0] if v else default

        upload_id = (one("uploadId") or "").strip()
        raw_lic_fn = (one("licenseFilename", "") or "").strip()
        # Only sanitize a real filename; sanitize_filename("") returns the
        # "upload.bin" fallback, which we don't want recorded as the source.
        src_filename = uploads.sanitize_filename(raw_lic_fn) if raw_lic_fn else ""
        if not upload_id or any(c in upload_id for c in ("/", "\\", "..")):
            self._send_json({"ok": False, "error": "valid uploadId query param required"}, 400)
            return
        meta = uploads.read_meta(upload_id)
        if not meta:
            self._send_json({"ok": False, "error": f"no image named '{upload_id}'"}, 404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0:
            self._send_json({"ok": False, "error": "Content-Length required"}, 411)
            return
        if content_length > uploads._LICENSE_MAX:  # noqa: SLF001
            self._send_json({"ok": False,
                             "error": "license file too large (expected a small key file)"}, 413)
            return
        raw = self.rfile.read(content_length)
        result = import_common.attach_license(upload_id, raw, raw_lic_fn)
        self._send_json(result, result.get("status", 200 if result.get("ok") else 400))

    def _handle_delete(self, q):
        def one(name):
            v = q.get(name, [None])
            return v[0] if v else None

        upload_id = one("uploadId")
        namespace = one("namespace")
        name = one("name")
        if not upload_id:
            self._send_json({"ok": False, "error": "uploadId query param required"}, 400)
            return
        meta = uploads.read_meta(upload_id)
        namespace = namespace or (meta or {}).get("namespace")
        names = import_common.collect_artifact_names(meta, name or upload_id)
        err = import_common.cleanup_existing(upload_id, namespace, name or upload_id)
        if err:
            self._send_json(err, err.get("status", 502))
            return
        logger.info("Delete %s/%s (%d artifact(s))", namespace, upload_id, len(names))
        invalidate_tracked_cache()
        _sync_app_status_now()
        self._send_json({"ok": True, "artifactDeleted": bool(namespace),
                         "localRemoved": True})

    def _handle_upload(self, q):
        """Single entry point for image uploads. Only vendor .zip files are
        accepted; the NOS (SR Linux vs SR OS) is auto-detected from the zip
        contents. The md5 and the YANG schema profile are taken/derived
        automatically -- the user supplies neither."""
        def one(name, default=None):
            v = q.get(name, [default])
            return v[0] if v else default

        filename = uploads.sanitize_filename(one("filename", ""))
        namespace = (one("namespace") or "").strip()
        name_override = (one("name") or "").strip()
        replace = (one("replace") or "").lower() in ("true", "1", "yes")
        if not filename:
            self._send_json({"ok": False, "error": "filename query param required"}, 400)
            return
        if not namespace:
            self._send_json({"ok": False, "error": "namespace query param required"}, 400)
            return
        if not filename.lower().endswith(".zip"):
            self._send_json({"ok": False,
                             "error": "Only vendor .zip images are supported "
                                      "(SR Linux or SR OS 7750 TiMOS)."}, 400)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0:
            self._send_json({"ok": False, "error": "Content-Length required"}, 411)
            return
        max_bytes = int(CONFIG.get("maxUploadMiB", 4096)) * 1024 * 1024

        # Stream the zip to a per-request temp area, auto-detect the NOS from its
        # contents, then dispatch. The temp area is always removed.
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(dir=UPLOAD_DIR, prefix=".incoming-")
        try:
            tmp_zip = os.path.join(tmp_dir, "upload.zip")
            try:
                uploads.stream_upload(self.rfile, content_length, tmp_zip, max_bytes)
            except uploads.UploadTooLarge as e:
                self._send_json({"ok": False, "error": f"upload too large: {e}"}, 413)
                return
            if not uploads.looks_like_zip(tmp_zip):
                self._send_json({"ok": False,
                                 "error": "the uploaded file is not a valid .zip archive"}, 400)
                return
            result = import_common.process_zip(tmp_dir, tmp_zip, filename, namespace,
                                               name_override, CONFIG, replace=replace)
            invalidate_tracked_cache()
            if result.get("ok"):
                _sync_app_status_now()
            self._send_json(result, result.get("status", 200 if result.get("ok") else 400))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)



def _nodeprofile_yaml(nos, version, namespace, prof_name, image_entries, yang_url,
                      license_cm=None):
    """A complete, copy-ready NodeProfile example for an Available image. The
    image path(s)+imageMd5, version, operatingSystem and yang are filled from the
    real artifact(s); environment-specific fields are left as <placeholders>.
    image_entries = [(image_path, md5_path_or_empty), ...]. When `license_cm` is
    set (a license was attached to this image), spec.license references the
    ConfigMap Image Manager created for it in eda-system."""
    L = [
        "apiVersion: core.eda.nokia.com/v1",
        "kind: NodeProfile",
        "metadata:",
        f"  name: {prof_name}",
        f"  namespace: {namespace}",
        "  labels:",
        '    eda.nokia.com/bootstrap: "true"',
        "spec:",
        "  annotate: false",
        f"  operatingSystem: {nos}",
        f"  version: {version}",
        "  port: 57400",
        "  # image(s) registered by EDA Image Manager:",
        "  images:",
    ]
    for path, md5_path in image_entries:
        L.append(f"  - image: {path}")
        if md5_path:
            L.append(f"    imageMd5: {md5_path}")
    if yang_url:
        L.append(f"  yang: {yang_url}")
    else:
        L.append(f"  # yang: https://eda-asvr.eda-system.svc/{namespace}/schemaprofiles/"
                 "<profile>/<profile>.zip   # add the matching schema profile")
    if license_cm:
        L.append(f"  license: {license_cm}   # ConfigMap (in eda-system) created by Image "
                 "Manager from your uploaded license key")
    L += [
        "  # llmDb: https://eda-asvr.eda-system.svc/<ns>/llm-dbs/<db>/<db>.tar.gz"
        "   # optional, EDA-provided per version",
        "  nodeUser: admin",
        "  onboardingUsername: admin",
        "  onboardingPassword: NokiaSrl1!",
        "  dhcp:",
        "    managementPoolv4: <your-ipv4-mgmt-pool>",
        "    dhcp4Options:",
        "    - option: 6-DomainNameServer",
        "      value:",
        "      - <dns-server-ip>",
        "    - option: 42-NTPServers",
        "      value:",
        "      - <ntp-server-ip>",
    ]
    return "\n".join(L)


_VER_RE = import_common._VER_RE  # noqa: SLF001 - shared regex, single source of truth

_ASVR_ONLY_REASON = (
    "No local copy on Image Manager PVC — only cached on eda-asvr; "
    "re-upload the vendor .zip to restore a durable copy."
)
_NO_LOCAL_REASON = "Local PVC files missing — re-upload to restore."


def _resolve_download_status(local_ok, cr_st):
    """Combine PVC bytes with Artifact CR status (PVC is the durable origin)."""
    cr_st = cr_st or {}
    ds = (cr_st.get("downloadStatus") or "").strip()
    reason = cr_st.get("statusReason") or ""
    if local_ok:
        if ds == "Available":
            return "Available", reason
        if ds in ("Error", "Failed"):
            return ds, reason
        if ds in ("InProgress", "Downloading", "Pending") or ds:
            return "InProgress", reason
        return "NoArtifact", reason
    if ds == "Available":
        return "AsvrOnly", _ASVR_ONLY_REASON
    if ds in ("Error", "Failed"):
        return ds, reason or _NO_LOCAL_REASON
    if ds in ("InProgress", "Downloading", "Pending"):
        return "InProgress", reason
    if ds:
        return "NoLocalCopy", reason or _NO_LOCAL_REASON
    return "NoLocalCopy", _NO_LOCAL_REASON


def _aggregate_download_status(statuses, reasons):
    """Worst-case aggregation for multi-artifact uploads."""
    if not statuses:
        return "NoArtifact", ""
    if any(s in ("Error", "Failed") for s in statuses):
        err_reasons = [r for s, r in zip(statuses, reasons) if s in ("Error", "Failed") and r]
        return "Error", "; ".join(err_reasons[:4])
    if any(s == "AsvrOnly" for s in statuses):
        return "AsvrOnly", _ASVR_ONLY_REASON
    if any(s == "NoLocalCopy" for s in statuses):
        return "NoLocalCopy", _NO_LOCAL_REASON
    if any(s == "NoArtifact" for s in statuses):
        return "NoArtifact", ""
    if statuses and all(s == "Available" for s in statuses):
        return "Available", ""
    if any(s == "InProgress" for s in statuses):
        prog = [r for s, r in zip(statuses, reasons) if s == "InProgress" and r]
        return "InProgress", "; ".join(prog[:4])
    return statuses[0], (reasons[0] if reasons else "")


def _single_row(m, status_by_key):
    """Tracked-list row for a one-file image (SR Linux .bin / raw upload)."""
    ns = m.get("namespace")
    upload_id = m.get("uploadId") or m.get("artifactName")
    local_ok = uploads.upload_has_local_bytes(m, upload_id)
    st = status_by_key.get((ns, m.get("artifactName")), {})
    md5_name = m.get("md5ArtifactName")
    md5_st = status_by_key.get((ns, md5_name), {}) if md5_name else {}
    img_ds, img_reason = _resolve_download_status(local_ok, st)
    md5_ds, md5_reason = _resolve_download_status(local_ok, md5_st) if md5_name else ("", "")
    yang = m.get("yang") or {}
    yst = status_by_key.get((ns, yang.get("artifactName")), {}) if yang.get("artifactName") else {}
    yang_ds, yang_reason = _resolve_download_status(local_ok, yst) if yang.get("artifactName") else (None, "")
    agg_statuses = [s for s in (img_ds, md5_ds, yang_ds) if s]
    agg_reasons = [r for r in (img_reason, md5_reason, yang_reason) if r]
    download_status, status_reason = _aggregate_download_status(agg_statuses, agg_reasons)
    # NodeProfile paths only when PVC + eda-asvr both report Available.
    image_path = (artifact.asvr_path(st.get("internalUrl", ""))
                  if img_ds == "Available" else "")
    md5_path = (artifact.asvr_path(md5_st.get("internalUrl", ""))
                if md5_ds == "Available" else "")
    display = m.get("displayName") or m.get("artifactName") or ""
    nos = m.get("nos") or "srl"
    yang_url = yst.get("internalUrl", "") if yang_ds == "Available" else ""
    lic = m.get("license") or {}
    license_cm = lic.get("configMap") or ""
    snippet = ""
    example = ""
    if image_path:
        snippet = "images:\n  - image: " + image_path
        if md5_path:
            snippet += "\n    imageMd5: " + md5_path
        if yang_url:
            snippet += "\nyang: " + yang_url
        if license_cm:
            snippet += "\nlicense: " + license_cm
        vm = _VER_RE.search(display)
        example = _nodeprofile_yaml(nos, vm.group(1) if vm else "<version>", ns,
                                    uploads.to_k8s_name(display) or "my-nodeprofile",
                                    [(image_path, md5_path)], yang_url, license_cm or None)
    return {
        "uploadId": m.get("uploadId"),
        "name": m.get("artifactName"),
        "displayName": display,
        "namespace": ns,
        "repo": m.get("repo"),
        "filePath": m.get("filePath"),
        "filename": m.get("filename"),
        "sizeBytes": m.get("sizeBytes"),
        "md5": m.get("md5"),
        "storedAt": m.get("storedAt"),
        "downloadStatus": download_status,
        "statusReason": status_reason,
        "localCopy": local_ok,
        "imagePath": image_path,
        "md5Path": md5_path,
        "snippet": snippet,
        "nodeProfileExample": example,
        "nos": nos,
        "yangStatus": yang_ds,
        "license": license_cm or None,
        "licenseNos": lic.get("nos"),
    }


def _group_row(m, status_by_key):
    """Tracked-list row for a multi-file image group (SR OS): one upload, several
    Artifacts. Status is aggregated; the NodeProfile snippet lists every image
    path (plus the yang: URL) once all parts report Available."""
    ns = m.get("namespace")
    upload_id = m.get("uploadId")
    local_ok = uploads.upload_has_local_bytes(m, upload_id)
    arts = m.get("artifacts") or []
    yang = m.get("yang") or None
    statuses, agg_reasons, image_lines, image_entries = [], [], [], []
    all_images_available = bool(arts)
    for a in arts:
        st = status_by_key.get((ns, a.get("artifactName")), {})
        ds, part_reason = _resolve_download_status(local_ok, st)
        statuses.append(ds)
        ipath = ""
        if ds == "Available":
            ipath = artifact.asvr_path(st.get("internalUrl", ""))
            if not ipath:
                all_images_available = False
        else:
            all_images_available = False
        if part_reason:
            agg_reasons.append((a.get("filename") or "") + ": " + part_reason)
        # per-file md5 artifact (SR OS imageMd5, from the zip's md5sums.txt)
        mpath = ""
        md5_name = a.get("md5ArtifactName")
        if md5_name:
            mst = status_by_key.get((ns, md5_name), {})
            mds, md5_reason = _resolve_download_status(local_ok, mst)
            statuses.append(mds)
            if mds == "Available":
                mpath = artifact.asvr_path(mst.get("internalUrl", ""))
            if md5_reason:
                agg_reasons.append((a.get("filename") or "") + ".md5: " + md5_reason)
        if ipath:
            image_lines.append("  - image: " + ipath
                               + ("\n    imageMd5: " + mpath if mpath else ""))
            image_entries.append((ipath, mpath))

    yang_status, yang_url = None, ""
    if yang:
        yst = status_by_key.get((ns, yang.get("artifactName")), {})
        yang_status, yang_reason = _resolve_download_status(local_ok, yst)
        statuses.append(yang_status)
        if yang_status == "Available":
            yang_url = yst.get("internalUrl", "")    # yang: takes a full asvr URL
        if yang_reason:
            agg_reasons.append("yang: " + yang_reason)

    agg, agg_reason = _aggregate_download_status(statuses, agg_reasons)

    lic = m.get("license") or {}
    license_cm = lic.get("configMap") or ""
    snippet = ""
    example = ""
    if all_images_available and image_lines:
        snippet = "images:\n" + "\n".join(image_lines)
        if yang_url:
            snippet += "\nyang: " + yang_url
        if license_cm:
            snippet += "\nlicense: " + license_cm
        example = _nodeprofile_yaml("sros", m.get("version") or "<version>", ns,
                                    m.get("uploadId") or "my-nodeprofile",
                                    image_entries, yang_url, license_cm or None)
    return {
        "uploadId": m.get("uploadId"),
        "name": m.get("uploadId"),
        "displayName": m.get("displayName") or m.get("uploadId"),
        "namespace": ns,
        "repo": m.get("repo"),
        "filePath": "",
        "sizeBytes": m.get("sizeBytes"),
        "storedAt": m.get("storedAt"),
        "downloadStatus": agg,
        "statusReason": agg_reason,
        "localCopy": local_ok,
        "snippet": snippet,
        "nodeProfileExample": example,
        "nos": "sros",
        "fileCount": len(arts),
        "yangStatus": yang_status,
        "license": license_cm or None,
        "licenseNos": lic.get("nos"),
    }


def _sim_nodeprofile_yaml(version, namespace, prof_name, container_image, yang_url,
                          license_cm=None):
    """A complete, copy-ready SR OS *simulator* NodeProfile: containerImage points
    at this app's /v2 endpoint. When `license_cm` is set (a license was pasted with
    this image) spec.license references the ConfigMap Image Manager already created
    in eda-system; otherwise the license line is left as a comment (no inline
    ConfigMap — Image Manager creates the ConfigMap itself when you paste a key).
    <…> values are for the operator to set."""
    L = [
        "apiVersion: core.eda.nokia.com/v1",
        "kind: NodeProfile",
        "metadata:",
        f"  name: {prof_name}",
        f"  namespace: {namespace}",
        "  labels:",
        '    eda.nokia.com/bootstrap: "true"',
        "spec:",
        "  operatingSystem: sros",
        f"  version: {version}",
        f"  containerImage: {container_image}",
        "  imagePullSecret: core      # a Secret in eda-system (where sims run); 'core' exists "
        "and works — this registry is anonymous, so its contents are unused",
    ]
    if license_cm:
        L.append(f"  license: {license_cm}      # ConfigMap (eda-system) created by Image Manager "
                 "from your pasted license key — already applied")
    else:
        L.append("  # license: <license-configmap>      # optional — paste a license key when you "
                 "upload the image and Image Manager creates + wires this for you")
    if yang_url:
        L.append(f"  yang: {yang_url}")
    else:
        L.append("  # yang: https://eda-asvr.eda-system.svc/<ns>/schemaprofiles/<p>/<p>.zip"
                 "   # add the matching SR OS schema profile")
    L += [
        "  nodeUser: admin",
        "  onboardingUsername: admin",
        "  onboardingPassword: NokiaSrl1!",
        "  dhcp:",
        "    managementPoolv4: <your-ipv4-mgmt-pool>",
    ]
    return "\n".join(L)


def _srsim_row(m, status_by_key):
    """Tracked-list row for an SR-SIM container image. Served from our own /v2
    endpoint (no eda-asvr Artifact), so it is Ready as soon as it is unpacked. The
    Details popup yields a copy-ready sim NodeProfile (containerImage)."""
    ns = m.get("namespace")
    artifact_name = m.get("artifactName")
    upload_id = m.get("uploadId") or artifact_name
    local_ok = uploads.upload_has_local_bytes(m, upload_id)
    tag = m.get("imageTag") or m.get("version") or "latest"
    version = m.get("version") or "<version>"
    container_image = f"{sim_registry_host()}/{artifact_name}:{tag}"
    yang = m.get("yang") or {}
    yst = status_by_key.get((ns, yang.get("artifactName")), {}) if yang.get("artifactName") else {}
    yang_ds, _ = _resolve_download_status(local_ok, yst) if yang.get("artifactName") else (None, "")
    yang_url = yst.get("internalUrl", "") if yang_ds == "Available" else ""
    lic = m.get("license") or {}
    license_cm = lic.get("configMap") or ""
    snippet = ("operatingSystem: sros\nversion: " + version
               + "\ncontainerImage: " + container_image
               + "\nimagePullSecret: core"
               + ("\nlicense: " + license_cm if license_cm else ""))
    example = _sim_nodeprofile_yaml(version, ns, artifact_name or "my-sim-nodeprofile",
                                    container_image, yang_url, license_cm or None)
    download_status = "Ready" if local_ok else "NoLocalCopy"
    status_reason = "" if local_ok else _NO_LOCAL_REASON
    return {
        "uploadId": m.get("uploadId"),
        "name": artifact_name,
        "displayName": m.get("displayName") or artifact_name,
        "namespace": ns,
        "repo": "served by Image Manager (/v2)",
        "filePath": "",
        "sizeBytes": m.get("sizeBytes"),
        "storedAt": m.get("storedAt"),
        "downloadStatus": download_status,
        "statusReason": status_reason,
        "localCopy": local_ok,
        "snippet": snippet if local_ok else "",
        "nodeProfileExample": example if local_ok else "",
        "nos": "srsim",
        "containerImage": container_image,
        "imageTag": tag,
        "yangStatus": yang_ds,
        "license": license_cm or None,
        "licenseNos": lic.get("nos"),
    }


def _artifact_fallback_rows(status_by_key, covered_keys):
    """Rows for managed Artifacts with no PVC meta (in-flight or asvr-only ghosts)."""
    groups = {}
    for art in artifact.list_managed_artifacts():
        md = art.get("metadata", {}) or {}
        ns = md.get("namespace", "")
        name = md.get("name", "")
        if name.endswith("-md5"):
            continue
        # A deleted upload's Artifact CR lingers in Terminating for a while;
        # without this check it would resurrect as a ghost "Available" row.
        if md.get("deletionTimestamp"):
            continue
        upload_id = artifact.upload_id_from_cr(art) or name
        key = (ns, upload_id)
        if key in covered_keys:
            continue
        spec = art.get("spec", {}) or {}
        st = status_by_key.get((ns, name), {})
        download_status, status_reason = _resolve_download_status(False, st)
        groups.setdefault(key, {
            "uploadId": upload_id,
            "name": name,
            "displayName": name,
            "namespace": ns,
            "repo": spec.get("repo", ""),
            "filePath": spec.get("filePath", ""),
            "sizeBytes": None,
            "storedAt": md.get("creationTimestamp", ""),
            "downloadStatus": download_status,
            "statusReason": status_reason,
            "localCopy": False,
            "externalUrl": st.get("externalUrl", ""),
        })
    return list(groups.values())


_server_scheme = [None]  # "https" | "http" | None; set by start_file_server


def server_state():
    """Self-reported UI reachability for the launcher dashboard (cable-map
    'http: Reachable' parity): Reachable when serving HTTPS, NoTLS when the
    cert never mounted, Down before the server thread starts."""
    if _server_scheme[0] == "https":
        return "Reachable"
    if _server_scheme[0] == "http":
        return "NoTLS"
    return "Down"


def invalidate_tracked_cache():
    """Drop cached artifact rows (call after upload/delete)."""
    with _tracked_lock:
        _tracked_cache["at"] = 0.0
        _tracked_cache["data"] = None


def build_tracked_list():
    """Merge PVC upload metadata with live Artifact download status for the UI."""
    now = time.time()
    with _tracked_lock:
        cached = _tracked_cache["data"]
        if cached is not None and now - _tracked_cache["at"] < _TRACKED_TTL:
            return cached
    rows = _build_tracked_list()
    with _tracked_lock:
        _tracked_cache["data"] = rows
        _tracked_cache["at"] = now
    return rows


def _build_tracked_list():
    # one cluster-wide list call, indexed by (namespace, name)
    status_by_key = {}
    try:
        for art in artifact.list_managed_artifacts():
            md = art.get("metadata", {})
            st = art.get("status", {}) or {}
            status_by_key[(md.get("namespace"), md.get("name"))] = st
    except Exception as e:
        logger.info("artifact list unavailable: %s", e)

    out = []
    covered = set()
    for m in uploads.list_meta():
        key = (m.get("namespace"), m.get("uploadId") or m.get("artifactName"))
        covered.add(key)
        if m.get("nos") == "srsim":
            out.append(_srsim_row(m, status_by_key))
        elif m.get("artifacts"):
            out.append(_group_row(m, status_by_key))
        else:
            out.append(_single_row(m, status_by_key))
    try:
        out.extend(_artifact_fallback_rows(status_by_key, covered))
    except Exception as e:
        logger.info("artifact fallback rows failed: %s", e)
    out.sort(key=lambda r: r.get("storedAt") or "", reverse=True)
    return out


def write_healthz(status="ok", last_reconcile=None, extra=None):
    """Atomic write of .healthz.json via rename."""
    payload = {"status": status, "last_reconcile": last_reconcile}
    if extra:
        payload.update(extra)
    data = json.dumps(payload)
    tmp = HEALTHZ_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(data)
    os.replace(tmp, HEALTHZ_FILE)


def _build_ssl_context():
    crt = os.path.join(TLS_DIR, "tls.crt")
    key = os.path.join(TLS_DIR, "tls.key")
    if not (os.path.isfile(crt) and os.path.isfile(key)):
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)
    return ctx


def start_file_server(port=8443):
    """Start the HTTPS file server as a daemon thread. Falls back to HTTP if no cert."""
    global _server
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    ctx = None
    try:
        ctx = _build_ssl_context()
    except Exception as e:
        logger.error("Failed to load serving cert from %s: %s", TLS_DIR, e)
    if ctx is not None:
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    else:
        logger.error("No serving cert at %s -- starting PLAIN HTTP (kubelet HTTPS "
                     "probes and eda-asvr HTTPS pulls will fail until cert present)",
                     TLS_DIR)
        scheme = "http"
    with _server_lock:
        _server = server
    _server_scheme[0] = scheme
    t = threading.Thread(target=server.serve_forever, daemon=True, name="fileserver")
    t.start()
    logger.info("File server started on %s://0.0.0.0:%d", scheme, port)
    return server


def stop_file_server():
    """Gracefully stop the HTTPS server (called on SIGTERM)."""
    global _server
    with _server_lock:
        server = _server
        _server = None
    if server is None:
        return
    try:
        write_healthz("shutting_down", None)
    except Exception:
        pass
    try:
        server.shutdown()
        logger.info("File server stopped")
    except Exception as e:
        logger.warning("File server shutdown error: %s", e)
