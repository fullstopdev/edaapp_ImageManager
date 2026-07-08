"""
Upload zip extraction helpers (grouped seam).

This module groups the upload "zip extraction" responsibilities so future
refactors can move code without touching callers. `uploads.py` keeps the
original public function names as re-exports.
"""

from uploads import (
    detect_nos_from_zip,
    extract_image_from_zip,
    detect_sros_version,
    extract_sros_images,
    extract_srsim_image,
    _parse_oci_layout,
    _srsim_member,
)

__all__ = [
    "detect_nos_from_zip",
    "extract_image_from_zip",
    "detect_sros_version",
    "extract_sros_images",
    "extract_srsim_image",
    "_parse_oci_layout",
    "_srsim_member",
]

