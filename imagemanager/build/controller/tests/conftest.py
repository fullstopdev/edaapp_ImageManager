"""Shared fixtures for controller unit tests."""

from __future__ import annotations

import hashlib
import io
import json
import lzma
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_upload_dir(monkeypatch):
    """Point uploads.DATA_DIR at a writable temp directory."""
    import uploads

    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(uploads, "DATA_DIR", d)
        yield Path(d)


def _make_jwt(payload: dict) -> str:
    import base64
    import time

    import jwt as pyjwt

    import auth

    keys, kid = _TEST_RSA_KEYPAIR[0], _TEST_RSA_KEYPAIR[1]
    private_key = keys

    now = int(time.time())
    p = dict(payload or {})
    p.setdefault("exp", now + 3600)
    # Default claims to the app's configured JWT trust boundary so tests focus
    # on the behavior under test rather than token plumbing.
    p.setdefault("iss", auth.JWT_ISSUER)
    p.setdefault("aud", auth.CLIENT_ID)
    p.setdefault("azp", auth.CLIENT_ID)

    tok = pyjwt.encode(
        p,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    return tok if isinstance(tok, str) else tok.decode("utf-8")


@pytest.fixture
def make_jwt():
    return _make_jwt


# --------------------------- auth test setup ---------------------------

# Shared RSA keypair for deterministic JWT verification in tests.
_TEST_RSA_KEYPAIR = [None, None]  # [private_key, kid]


@pytest.fixture(scope="session", autouse=True)
def _init_test_rsa_keypair():
    import base64

    from cryptography.hazmat.primitives.asymmetric import rsa

    # Generate once per test run so token signatures stay consistent.
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    kid = "test-kid"

    def b64u_int(i: int) -> str:
        b = i.to_bytes((i.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).decode().rstrip("=")

    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": b64u_int(public_numbers.n),
        "e": b64u_int(public_numbers.e),
    }
    jwks = {"keys": [jwk]}

    _TEST_RSA_KEYPAIR[0] = private_key
    _TEST_RSA_KEYPAIR[1] = kid

    import auth

    # Patch auth's JWKS fetch to avoid any network calls.
    auth._fetch_jwks = lambda: jwks  # type: ignore[assignment]
    auth._jwks_cache["keys"] = None
    auth._jwks_cache["exp"] = 0.0

    return None


def make_srl_zip(dest: Path, *, bin_name: str = "image.bin", md5: str | None = "a" * 32) -> Path:
    """Minimal SR Linux vendor zip with one .bin and optional .md5 sidecar."""
    zip_path = dest / "srl.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(bin_name, b"fake-srl-image-bytes")
        if md5:
            zf.writestr(f"{bin_name}.md5", f"{md5}  {bin_name}\n")
    return zip_path


def make_sros_zip(dest: Path, version: str = "26.3.R3") -> Path:
    """Minimal SR OS TiMOS vendor zip with the canonical boot-file set."""
    zip_path = dest / "sros.zip"
    prefix = f"cflash/TiMOS-SR-{version}/"
    md5_lines = []
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in ("boot.ldr", "both.tim", "cpm.tim", "iom.tim", "kernel.tim", "support.tim"):
            rel = prefix + name
            zf.writestr(rel, f"timos-{name}".encode())
            md5_lines.append(f"{'b' * 32}  {rel}")
        zf.writestr("cflash/md5sums.txt", "\n".join(md5_lines) + "\n")
    return zip_path


def make_minimal_oci_tarxz() -> bytes:
    """Tiny OCI layout (config + one layer) packaged as .tar.xz for SR-SIM tests."""
    config = {"schemaVersion": 2, "config": {}, "layers": []}
    config_bytes = json.dumps(config).encode()
    config_digest = hashlib.sha256(config_bytes).hexdigest()

    layer_bytes = b"layer-payload"
    layer_digest = hashlib.sha256(layer_bytes).hexdigest()

    manifest = {
        "schemaVersion": 2,
        "config": {"digest": f"sha256:{config_digest}", "size": len(config_bytes)},
        "layers": [{"digest": f"sha256:{layer_digest}", "size": len(layer_bytes)}],
    }
    manifest_bytes = json.dumps(manifest).encode()
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()

    index = {
        "schemaVersion": 2,
        "manifests": [{
            "digest": f"sha256:{manifest_digest}",
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "annotations": {"org.opencontainers.image.ref.name": "26.3.R3"},
        }],
    }
    manifest_json = [{"RepoTags": ["localhost/nokia/srsim:26.3.R3"]}]

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w|") as tar:
        for name, data in (
            ("index.json", json.dumps(index).encode()),
            ("manifest.json", json.dumps(manifest_json).encode()),
            ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}\n'),
            (f"blobs/sha256/{config_digest}", config_bytes),
            (f"blobs/sha256/{layer_digest}", layer_bytes),
            (f"blobs/sha256/{manifest_digest}", manifest_bytes),
        ):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return lzma.compress(buf.getvalue())


def make_srsim_zip(dest: Path) -> Path:
    """Minimal SR-SIM vendor zip containing vm/SR-Simulator/srsim.tar.xz."""
    zip_path = dest / "srsim.zip"
    tarxz = make_minimal_oci_tarxz()
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("vm/SR-Simulator/srsim.tar.xz", tarxz)
    return zip_path


@pytest.fixture
def srl_zip(tmp_path):
    return make_srl_zip(tmp_path)


@pytest.fixture
def sros_zip(tmp_path):
    return make_sros_zip(tmp_path)


@pytest.fixture
def srsim_zip(tmp_path):
    return make_srsim_zip(tmp_path)
