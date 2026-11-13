"""Track B: 파일 검증·저장, Receipt 조회."""

from io import BytesIO
import uuid
import warnings
from typing import Optional

from PIL import Image, UnidentifiedImageError
from sqlmodel import Session, select

from app.common.exceptions import AppException
from app.core.config import settings
from app.receipts.models import Receipt
from app.receipts.schemas import ReceiptOut, ReceiptSummary
from app.receipts.storage import FileStorage, LocalFileStorage, S3FileStorage


def detect_image_type(file_bytes: bytes) -> tuple[str, str] | None:
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    return None


def _decode_image(file_bytes: bytes, media_type: str) -> None:
    expected_format = {"image/jpeg": "JPEG", "image/png": "PNG"}.get(media_type)
    if expected_format is None:
        raise AppException(400, "VALIDATION_ERROR", "지원하지 않는 이미지 형식입니다.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(file_bytes)) as image:
                if image.format != expected_format:
                    raise AppException(
                        400,
                        "VALIDATION_ERROR",
                        "파일 형식과 실제 이미지 형식이 일치하지 않습니다.",
                    )
                width, height = image.size
                if (
                    width <= 0
                    or height <= 0
                    or width * height > settings.MAX_IMAGE_PIXELS
                ):
                    raise AppException(
                        400,
                        "VALIDATION_ERROR",
                        "이미지 픽셀 수 제한을 초과했습니다.",
                    )
                image.verify()

            # verify()는 구조 검사를 수행하므로, 별도로 실제 디코딩도 한다.
            with Image.open(BytesIO(file_bytes)) as image:
                image.load()
    except AppException:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise AppException(
            400,
            "VALIDATION_ERROR",
            "읽을 수 없는 손상된 이미지입니다.",
        ) from exc


def validate_image(file_bytes: bytes, content_type: Optional[str]) -> tuple[str, str]:
    if not file_bytes:
        raise AppException(400, "VALIDATION_ERROR", "빈 파일은 업로드할 수 없습니다.")
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise AppException(400, "VALIDATION_ERROR", "파일 크기 제한을 초과했습니다.")

    detected = detect_image_type(file_bytes)
    if detected is None:
        raise AppException(400, "VALIDATION_ERROR", "지원하지 않는 이미지 형식입니다.")
    detected_type, extension = detected
    if content_type and content_type not in {detected_type, "application/octet-stream"}:
        raise AppException(
            400,
            "VALIDATION_ERROR",
            "파일 형식과 내용이 일치하지 않습니다.",
        )
    _decode_image(file_bytes, detected_type)
    return detected_type, extension


storage: FileStorage = (
    S3FileStorage(settings.S3_BUCKET, settings.AWS_REGION)
    if settings.S3_BUCKET
    else LocalFileStorage(settings.STORAGE_DIR)
)


def _delete_after_failure(key: str) -> None:
    try:
        storage.delete(key)
    except Exception:
        # 원래 오류를 보존한다. 저장소 정리는 best effort이다.
        pass


def list_receipts(session: Session, user_id: uuid.UUID) -> list[ReceiptSummary]:
    statement = (
        select(Receipt)
        .where(Receipt.user_id == user_id)
        .order_by(Receipt.created_at.desc(), Receipt.id.desc())
    )
    return [ReceiptSummary.model_validate(item) for item in session.exec(statement).all()]


def get_receipt(session: Session, user_id: uuid.UUID, receipt_id: int) -> ReceiptOut:
    statement = select(Receipt).where(
        Receipt.id == receipt_id, Receipt.user_id == user_id
    )
    receipt = session.exec(statement).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    return ReceiptOut.model_validate(receipt)
