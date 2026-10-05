"""File identity and DCT perceptual similarity; neither proves transaction identity."""
from io import BytesIO
import hashlib
import math
from statistics import median
from PIL import Image, ImageOps


def image_fingerprints(content: bytes) -> tuple[str, str]:
    with Image.open(BytesIO(content)) as original:
        image = ImageOps.exif_transpose(original).convert("L").resize((32, 32), Image.Resampling.LANCZOS)
        pixels = list(image.get_flattened_data())
    cosines = [[math.cos((2 * position + 1) * frequency * math.pi / 64) for position in range(32)] for frequency in range(8)]
    horizontal = [[sum(pixels[y * 32 + x] * cosines[u][x] for x in range(32)) for u in range(8)] for y in range(32)]
    coefficients = [sum(horizontal[y][u] * cosines[v][y] for y in range(32)) for v in range(8) for u in range(8)]
    threshold = median(coefficients[1:])
    bits = sum(int(value > threshold) << index for index, value in enumerate(coefficients[1:]))
    return hashlib.sha256(content).hexdigest(), f"{bits:016x}"


def backfill_image_fingerprints(session, storage, *, user_id=None) -> dict:
    """Fill missing legacy hashes and refresh candidates in the caller's transaction.

    This is an explicit local maintenance operation, not an OCR call or a file rewrite.
    """
    from sqlalchemy import or_, update
    from sqlmodel import select
    from app.receipts.models import Receipt
    from app.receipts.transactions import find_duplicates
    statement = select(Receipt).where(or_(Receipt.file_hash.is_(None), Receipt.perceptual_hash.is_(None)))
    if user_id is not None:
        statement = statement.where(Receipt.user_id == user_id)
    updated, skipped = [], []
    for receipt in session.exec(statement.order_by(Receipt.id)).all():
        previous_sha, previous_phash, revision = receipt.file_hash, receipt.perceptual_hash, receipt.revision
        try:
            content, _ = storage.read(receipt.image_url)
            sha, phash = image_fingerprints(content)
        except (OSError, ValueError) as error:
            skipped.append({"receipt_id": receipt.id, "reason": "IMAGE_UNAVAILABLE", "error_type": type(error).__name__})
            continue
        if previous_sha is not None and previous_sha != sha:
            skipped.append({"receipt_id": receipt.id, "reason": "SOURCE_HASH_MISMATCH"})
            continue
        result = session.execute(update(Receipt).where(Receipt.id == receipt.id, Receipt.user_id == receipt.user_id,
            Receipt.revision == revision, Receipt.image_url == receipt.image_url,
            Receipt.file_hash == previous_sha, Receipt.perceptual_hash == previous_phash).values(
                file_hash=sha if previous_sha is None else previous_sha,
                perceptual_hash=phash if previous_phash is None else previous_phash))
        if result.rowcount != 1:
            skipped.append({"receipt_id": receipt.id, "reason": "CHANGED_DURING_BACKFILL"})
            continue
        session.refresh(receipt)
        updated.append(receipt)
    for receipt in updated:
        find_duplicates(session, receipt)
    return {"updated_count": len(updated), "updated_receipt_ids": [r.id for r in updated], "skipped": skipped}
