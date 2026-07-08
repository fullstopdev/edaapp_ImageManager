"""
Upload licensing helpers (grouped seam).

`uploads.py` keeps public function names as re-exports.
"""

from uploads import (
    normalize_license,
    is_valid_license,
    detect_license_nos,
    license_cm_name,
    set_license_meta,
    store_license_file,
)

__all__ = [
    "normalize_license",
    "is_valid_license",
    "detect_license_nos",
    "license_cm_name",
    "set_license_meta",
    "store_license_file",
]

