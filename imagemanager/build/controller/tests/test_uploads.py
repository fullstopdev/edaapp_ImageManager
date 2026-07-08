"""Unit tests for uploads.py pure-logic helpers."""

from __future__ import annotations

import uploads
from conftest import make_minimal_oci_tarxz, make_srl_zip, make_sros_zip, make_srsim_zip


def test_sanitize_filename_strips_path_and_unsafe_chars():
    assert uploads.sanitize_filename(r"..\..\evil\Nokia-7220.zip") == "Nokia-7220.zip"
    assert uploads.sanitize_filename("foo bar?.zip") == "foo_bar_.zip"
    assert uploads.sanitize_filename("") == "upload.bin"


def test_derive_name_srlinux_and_srsim():
    assert uploads.derive_name("Nokia-7220_IXR_SR_Linux-h1-26.3.2.zip") == "srlinux-26.3.2"
    assert uploads.derive_name("Nokia-SR-SIM-26.3.R3.zip") == "srsim-26.3.r3"
    assert uploads.derive_name("custom-image.bin") == "custom-image"


def test_to_k8s_name():
    assert uploads.to_k8s_name("SR Linux 26.3.2") == "sr-linux-26.3.2"
    assert uploads.to_k8s_name("--weird--") == "weird"


def test_looks_like_zip(tmp_path):
    good = tmp_path / "good.zip"
    good.write_bytes(b"PK\x03\x04" + b"\x00" * 10)
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"not-a-zip")
    assert uploads.looks_like_zip(str(good)) is True
    assert uploads.looks_like_zip(str(bad)) is False
    assert uploads.looks_like_zip("/no/such/file") is False


def test_parse_md5_text_and_sums():
    assert uploads.parse_md5_text("deadbeef" * 4 + "  image.bin") == "deadbeef" * 4
    text = (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  ./cflash/TiMOS-SR-26.3.R3/both.tim\n"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  cflash/boot.ldr\n"
    )
    by_path, by_base = uploads.parse_md5sums(text)
    assert by_path["TiMOS-SR-26.3.R3/both.tim"] == "a" * 32
    assert by_path["boot.ldr"] == "b" * 32
    assert by_base["both.tim"] == "a" * 32


def test_norm_md5_path():
    assert uploads._norm_md5_path("./cflash/foo.tim") == "foo.tim"
    assert uploads._norm_md5_path("cflash/foo.tim") == "foo.tim"


def test_detect_nos_from_zip(tmp_path):
    srl = make_srl_zip(tmp_path)
    sros = make_sros_zip(tmp_path, version="26.3.R3")
    srsim = make_srsim_zip(tmp_path)
    assert uploads.detect_nos_from_zip(str(srl)) == "srl"
    assert uploads.detect_nos_from_zip(str(sros)) == "sros"
    assert uploads.detect_nos_from_zip(str(srsim)) == "srsim"


def test_detect_sros_version():
    members = ["cflash/TiMOS-SR-26.3.R3/both.tim", "cflash/md5sums.txt"]
    assert uploads.detect_sros_version(members) == "26.3.R3"
    assert uploads.detect_sros_version(["cflash/boot.ldr"]) is None


def test_extract_image_from_zip(tmp_path):
    z = make_srl_zip(tmp_path, bin_name="Nokia.bin", md5="c" * 32)
    dest = tmp_path / "out"
    dest.mkdir()
    name, md5 = uploads.extract_image_from_zip(str(z), str(dest))
    assert name == "Nokia.bin"
    assert md5 == "c" * 32
    assert (dest / "Nokia.bin").is_file()
    assert not z.exists()


def test_extract_sros_images(tmp_path):
    z = make_sros_zip(tmp_path)
    dest = tmp_path / "sros-out"
    dest.mkdir()
    version, files = uploads.extract_sros_images(str(z), str(dest))
    assert version == "26.3.R3"
    names = {f["filename"] for f in files}
    assert "both.tim" in names
    assert all((dest / n).is_file() for n in names)


def test_extract_srsim_image(tmp_path):
    z = make_srsim_zip(tmp_path)
    dest = tmp_path / "srsim-out"
    dest.mkdir()
    info = uploads.extract_srsim_image(str(z), str(dest))
    assert info["tag"] == "26.3.R3"
    assert info["blobCount"] >= 1
    assert (dest / "index.json").is_file()


def test_parse_oci_layout(tmp_path):
    dest = tmp_path / "oci"
    blobs = dest / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    tarxz = make_minimal_oci_tarxz()
    # Reuse the helper's layout by extracting the tar.xz manually.
    import io
    import lzma
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(lzma.decompress(tarxz)), mode="r|") as tar:
        for m in tar:
            if not m.isfile():
                continue
            rel = m.name.lstrip("./")
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(m) as src, open(out, "wb") as dst:
                dst.write(src.read())
    parsed = uploads._parse_oci_layout(str(dest))
    assert parsed["tag"] == "26.3.R3"
    assert parsed["manifestDigest"].startswith("sha256:")
    assert parsed["configDigest"]
    assert parsed["layerDigests"]


def test_normalize_license_and_detect():
    raw = 'license: "12345678-1234-1234-1234-123456789012 ABCDEFGHIJKLMNOP+/="\n'
    norm = uploads.normalize_license(raw)
    assert "12345678-1234-1234-1234-123456789012" in norm
    assert uploads.is_valid_license(raw) is True
    assert uploads.is_valid_license("no license here") is False
    assert uploads.detect_license_nos("# SRL_26_3_license", "srl.key") == "srl"
    assert uploads.detect_license_nos("# NOKIA BELL NV", "timos.key") == "sros"
