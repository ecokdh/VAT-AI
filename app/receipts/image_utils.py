"""Safe receipt image preprocessing utilities.

Includes EXIF auto-transposition and orientation validation guards to correct sideways receipts
while strictly preserving normal table-laid receipts to avoid regressions.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Tuple, Dict, Any
from PIL import Image, ImageOps


def apply_safe_receipt_orientation(
    image_bytes: bytes,
    mime_type: str = "image/jpeg"
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Safely preprocesses receipt image orientation:
    1. EXIF orientation check (tag 274):
       If EXIF indicates rotation/flip, normalize via exif_transpose and preserve result.
    2. Aspect ratio & orientation analysis:
       - If ratio >= 1.7 (extreme landscape like KR13), candidate orientation is 90 deg clockwise.
       - Normal landscape receipts (ratio 1.3~1.4) are strictly kept intact.
    3. Re-compression optimization:
       - If no EXIF change and no rotation applied, return EXACT original bytes without recompressing.
    4. Hashes and coordinate space:
       - Records original_sha256, processed_sha256, transform_history, coordinate_space.
    """
    orig_hash = hashlib.sha256(image_bytes).hexdigest()
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            orig_w, orig_h = img.size
            orig_ratio = orig_w / orig_h if orig_h else 1.0
            img_format = img.format if img.format in ("JPEG", "PNG") else ("PNG" if "png" in mime_type.lower() else "JPEG")

            # Check EXIF tag 274
            exif = img.getexif()
            exif_orientation = exif.get(274, 1) if exif else 1
            has_exif_transform = (exif_orientation not in (1, None))

            if has_exif_transform:
                transposed = ImageOps.exif_transpose(img)
                w, h = transposed.size
            else:
                transposed = img
                w, h = orig_w, orig_h

            ratio = w / h if h else 1.0
            rotation_applied = 0
            reason = "standard_portrait"
            oriented = transposed

            # Orientation guard
            if ratio >= 1.7:
                # Extreme landscape receipt (e.g. KR13 ratio 2.0)
                oriented = transposed.transpose(Image.Transpose.ROTATE_270)
                rotation_applied = 90
                reason = "extreme_landscape_ratio_guard"
            elif ratio > 1.0:
                reason = "normal_landscape_table_preserved"
            else:
                reason = "portrait_preserved"

            # Re-compression avoidance: if neither EXIF nor rotation changed the pixels, keep original bytes!
            if not has_exif_transform and rotation_applied == 0:
                out_bytes = image_bytes
            else:
                out_buf = BytesIO()
                oriented.save(out_buf, format=img_format)
                out_bytes = out_buf.getvalue()

            proc_hash = hashlib.sha256(out_bytes).hexdigest()

            return out_bytes, {
                "original_sha256": orig_hash,
                "processed_sha256": proc_hash,
                "original_size": [orig_w, orig_h],
                "original_ratio": round(orig_ratio, 2),
                "final_size": list(oriented.size),
                "final_ratio": round(oriented.width / oriented.height, 2),
                "exif_orientation_tag": exif_orientation,
                "exif_transformed": has_exif_transform,
                "rotation_applied_deg": rotation_applied,
                "coordinate_space": "rotated_90_cw" if rotation_applied == 90 else "original",
                "bytes_recompressed": (out_bytes != image_bytes),
                "mime_type": mime_type,
                "reason": reason,
            }
    except Exception as exc:
        return image_bytes, {
            "original_sha256": orig_hash,
            "processed_sha256": orig_hash,
            "rotation_applied_deg": 0,
            "exif_transformed": False,
            "coordinate_space": "original",
            "bytes_recompressed": False,
            "mime_type": mime_type,
            "reason": f"fallback_non_image_or_error: {str(exc)[:100]}",
        }
