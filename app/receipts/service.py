"""Track B: 파일 검증·저장, CLOVA OCR, Receipt CRUD."""

from io import BytesIO
import uuid
import warnings
from typing import Optional

from PIL import Image, UnidentifiedImageError
from sqlmodel import Session, select

from app.common.exceptions import AppException
from app.core.config import settings
from app.receipts import ocr_client
from app.receipts.models import Receipt
from app.receipts.schemas import ReceiptOut, ReceiptSummary
from app.receipts.storage import FileStorage, LocalFileStorage


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


storage: FileStorage = LocalFileStorage(settings.STORAGE_DIR)


def _delete_after_failure(key: str) -> None:
    try:
        storage.delete(key)
    except OSError:
        # 원래 오류를 보존한다. 저장소 정리는 best effort이다.
        pass


def _rollback_best_effort(session: Session) -> None:
    try:
        session.rollback()
    except Exception:
        # 원래 DB 오류와 파일 보존/정리 정책을 덮어쓰지 않는다.
        pass


def _ocr_is_complete(result: object) -> bool:
    return (
        isinstance(result, ocr_client.OcrResult)
        and bool(result.vendor.strip())
        and result.amount is not None
        and result.date is not None
        and bool(result.ocr_raw.strip())
    )


async def upload_receipt(
    session: Session,
    user_id: uuid.UUID,
    file_bytes: bytes,
    content_type: Optional[str],
) -> ReceiptOut:
    media_type, extension = validate_image(file_bytes, content_type)
    try:
        stored = storage.save(user_id, file_bytes, media_type, extension)
    except OSError as exc:
        raise AppException(500, "STORAGE_ERROR", "파일 저장에 실패했습니다.") from exc

    try:
        ocr_result = await ocr_client.extract_receipt(file_bytes, media_type)
    except Exception:
        # 예상된 외부 오류는 ocr_client가 None으로 변환한다. 그 밖의 오류는
        # 서버 오류로 남겨 OCR 실패로 위장하지 않는다.
        _delete_after_failure(stored.key)
        raise

    if _ocr_is_complete(ocr_result):
        receipt = Receipt(
            user_id=user_id,
            image_url=stored.key,
            ocr_raw=ocr_result.ocr_raw,
            vendor=ocr_result.vendor,
            amount=ocr_result.amount,
            date=ocr_result.date,
            status="done",
        )
    else:
        receipt = Receipt(
            user_id=user_id,
            image_url=stored.key,
            ocr_raw=None,
            vendor=None,
            amount=None,
            date=None,
            status="failed",
        )

    # flush 실패는 commit 전에 확정된 DB 저장 실패이므로 저장 파일을 정리한다.
    try:
        session.add(receipt)
        session.flush()
    except Exception as exc:
        _rollback_best_effort(session)
        _delete_after_failure(stored.key)
        raise AppException(500, "DATABASE_ERROR", "영수증 저장에 실패했습니다.") from exc

    # commit()이 예외를 던져도 서버/네트워크 상태에 따라 커밋 여부가
    # 불확실할 수 있다. 이 경우 참조 레코드가 이미 있을 수 있으므로 파일을
    # 삭제하지 않고 DB 오류만 반환한다.
    try:
        session.commit()
    except Exception as exc:
        _rollback_best_effort(session)
        raise AppException(500, "DATABASE_ERROR", "영수증 저장에 실패했습니다.") from exc

    # 여기부터는 Receipt가 이미 커밋되었다. refresh/응답 변환 실패 시에도
    # 커밋된 레코드가 참조하는 원본 파일을 삭제하지 않는다.
    try:
        session.refresh(receipt)
        return ReceiptOut.model_validate(receipt)
    except Exception as exc:
        _rollback_best_effort(session)
        raise AppException(500, "DATABASE_ERROR", "영수증 응답 생성에 실패했습니다.") from exc


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
