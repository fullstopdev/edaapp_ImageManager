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

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    header = b64(b'{"alg":"none","typ":"JWT"}')
    body = b64(json.dumps(payload).encode())
    return f"{header}.{body}.sig"


@pytest.fixture
def make_jwt():
    return _make_jwt


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
