"""Track B: 파일 검증·저장, 품질 확인, CLOVA OCR, Receipt CRUD."""

from io import BytesIO
import json
import math
import uuid
import warnings
from typing import Optional

from sqlalchemy import update as sa_update

from PIL import Image, UnidentifiedImageError
from sqlmodel import Session, select

from app.common.exceptions import AppException
from app.core.config import settings
from app.receipts import ocr_client
from app.receipts.models import Receipt, LineItem
from app.receipts.document import StructuredItem, DocumentFacts, complete_item
from app.receipts.money import MONEY_FIELDS, NEW_FIELDS, complete_money, complete_unit_price, money_problem, structured_money, unit_price_problem
from app.receipts.quality import inspect_receipt_image
from app.receipts.fingerprints import image_fingerprints
from app.receipts.schemas import ReceiptConfirmIn, ReceiptOcrUpdate, ReceiptOut, ReceiptSummary
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

    quality = inspect_receipt_image(file_bytes)
    if not quality.ok:
        receipt = Receipt(
            user_id=user_id,
            image_url=stored.key,
            ocr_raw=None,
            vendor=None,
            amount=None,
            date=None,
            status="retake",
            money_schema_version=2,
            quality_reason=" ".join(quality.reasons),
            confirmed=False,
        )
        receipt.file_hash, receipt.perceptual_hash = image_fingerprints(file_bytes)
        return _persist_receipt(session, stored.key, receipt)

    try:
        ocr_result = await ocr_client.extract_receipt(file_bytes, media_type)
    except Exception:
        # 예상된 외부 오류는 ocr_client가 None으로 변환한다. 그 밖의 오류는
        # 서버 오류로 남겨 OCR 실패로 위장하지 않는다.
        _delete_after_failure(stored.key)
        raise

    if isinstance(ocr_result, ocr_client.OcrResult):
        snapshot = _ocr_snapshot(ocr_result)
        receipt = Receipt(
            user_id=user_id,
            image_url=stored.key,
            ocr_raw=ocr_result.ocr_raw,
            vendor=ocr_result.vendor,
            amount=ocr_result.amount,
            date=ocr_result.date,
            status="done",
            business_number=ocr_result.business_number,
            supply_amount=ocr_result.supply_amount,
            vat_amount=ocr_result.vat_amount,
            items_json=json.dumps(list(ocr_result.items), ensure_ascii=False)
            if ocr_result.items
            else None,
            ocr_original=json.dumps(snapshot, ensure_ascii=False),
            confirmed=False,
        )
    elif isinstance(ocr_result, ocr_client.PartialRead):
        snapshot = _ocr_snapshot(ocr_result)
        receipt = Receipt(
            user_id=user_id,
            image_url=stored.key,
            ocr_raw=ocr_result.ocr_raw or None,
            vendor=ocr_result.vendor,
            amount=ocr_result.amount,
            date=ocr_result.date,
            status="needs_edit",
            business_number=ocr_result.business_number,
            supply_amount=ocr_result.supply_amount,
            vat_amount=ocr_result.vat_amount,
            items_json=json.dumps(list(ocr_result.items), ensure_ascii=False)
            if ocr_result.items
            else None,
            ocr_original=json.dumps(snapshot, ensure_ascii=False),
            confirmed=False,
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
            confirmed=False,
        )

    if isinstance(ocr_result, (ocr_client.OcrResult, ocr_client.PartialRead)):
        printed = {field: getattr(ocr_result, field, None) for field in NEW_FIELDS}
        printed["vat_amount"] = ocr_result.vat_amount
        printed["amount"] = ocr_result.amount
        printed["supply_amount"] = ocr_result.supply_amount
        sources = {field: {"kind": "printed", **(ocr_result.money_evidence or {}).get(field,
            {"state": "READ", "boxes": [], "confidence": None})} for field, value in printed.items() if value is not None}
        for field, evidence in (ocr_result.money_evidence or {}).items():
            if printed.get(field) is None:
                sources[field] = {"kind": "printed", **evidence}
        completed, sources = complete_money(printed, sources, allow_signed=bool((ocr_result.document or {}).get("adjustment_type")))
        for field, value in completed.items():
            setattr(receipt, field, value)
        receipt.money_sources_json = json.dumps(sources, ensure_ascii=False)
        rows = [complete_unit_price(row) for row in ocr_result.item_amounts]
        receipt.item_amounts_json = json.dumps(rows, ensure_ascii=False) if rows else None
        receipt.ocr_response_json = json.dumps(ocr_result.raw_response, ensure_ascii=False) if ocr_result.raw_response is not None else None
        metadata = dict(ocr_result.document or {})
        metadata["review_reasons"] = list(dict.fromkeys([*metadata.get("review_reasons", []), *ocr_result.review_reasons]))
        receipt.document_json = DocumentFacts.model_validate(metadata).model_dump_json()
    receipt.money_schema_version = 2
    receipt.file_hash, receipt.perceptual_hash = image_fingerprints(file_bytes)
    return _persist_receipt(session, stored.key, receipt, list(ocr_result.line_items) if isinstance(ocr_result, (ocr_client.OcrResult, ocr_client.PartialRead)) else None)


def _ocr_snapshot(result: ocr_client.OcrResult | ocr_client.PartialRead) -> dict:
    return {
        "vendor": result.vendor,
        "amount": result.amount,
        "date": result.date.isoformat() if result.date else None,
        "business_number": result.business_number,
        "supply_amount": result.supply_amount,
        "vat_amount": result.vat_amount,
        "items": list(result.items),
        "ocr_raw": result.ocr_raw,
        "text_boxes": list(result.text_boxes),
        **{field: getattr(result, field, None) for field in NEW_FIELDS},
        "item_amounts": list(result.item_amounts),
        "line_items": list(result.line_items),
        "review_reasons": list(result.review_reasons),
        "document": dict(result.document or {}),
        "money_evidence": dict(result.money_evidence or {}),
    }


def _persist_receipt(session: Session, stored_key: str, receipt: Receipt, line_items: list[dict] | None = None) -> ReceiptOut:
    # flush 실패는 commit 전에 확정된 DB 저장 실패이므로 저장 파일을 정리한다.
    try:
        session.add(receipt)
        session.flush()
        if line_items:
            _save_line_items(session, receipt, line_items, trusted_ocr=True)
        from app.receipts.transactions import find_duplicates
        find_duplicates(session, receipt)
    except Exception as exc:
        _rollback_best_effort(session)
        _delete_after_failure(stored_key)
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
    return ReceiptOut.model_validate(_owned_receipt(session, user_id, receipt_id))


def get_receipt_image(session: Session, user_id: uuid.UUID, receipt_id: int) -> tuple[bytes, str]:
    receipt = _owned_receipt(session, user_id, receipt_id)
    try:
        return storage.read(receipt.image_url)
    except OSError as exc:
        raise AppException(404, "NOT_FOUND", "원본 사진을 찾을 수 없습니다.") from exc


def _owned_receipt(session: Session, user_id: uuid.UUID, receipt_id: int) -> Receipt:
    statement = select(Receipt).where(
        Receipt.id == receipt_id, Receipt.user_id == user_id
    )
    receipt = session.exec(statement).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    return receipt


def _reject_negative_money(data: dict, *, allow_signed: bool = False) -> None:
    labels = {
        "amount": "총액",
        "supply_amount": "공급가액",
        "vat_amount": "부가세",
        "taxable_supply_amount": "과세 공급가액",
        "tax_exempt_amount": "면세 금액",
        "transaction_amount": "거래 총액",
        "payment_amount": "결제금액",
        "subtotal_amount": "할인 전 합계",
    }
    for key, label in labels.items():
        if key not in data or data[key] is None:
            continue
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value < 0 and not allow_signed):
            raise AppException(400, "VALIDATION_ERROR", f"{label}은 0 이상이어야 합니다.")


def _manual_states(values: dict, sources: dict, states: dict, *, inherited: bool = False) -> None:
    for field, state in states.items():
        present = values.get(field) is not None and values.get(field) != ""
        previous = sources.get(field, {})
        if inherited and state == "READ" and not present and previous.get("state") == "UNREVIEWED":
            continue
        if state == "READ" and not present or state in ("ABSENT", "FAILED", "NOT_APPLICABLE") and present:
            raise AppException(400, "VALIDATION_ERROR", "값 상태와 입력값이 맞지 않습니다. 미기재·판독 실패·해당 없음은 빈칸으로 저장하세요.")
        if state != previous.get("state"):
            sources[field] = {"kind": "manual", "state": state, "boxes": previous.get("boxes", []), "confidence": None}


def _edited_document(receipt: Receipt, incoming: dict) -> dict:
    previous = DocumentFacts.model_validate_json(receipt.document_json or "{}").model_dump(mode="json")
    if "date_candidates" in incoming and incoming["date_candidates"] != previous["date_candidates"]:
        raise AppException(400, "VALIDATION_ERROR", "원본 날짜 후보와 OCR 근거는 수정할 수 없습니다. 확인한 날짜를 별도 날짜 칸에 입력하세요.")
    data = DocumentFacts.model_validate({**previous, **incoming}).model_dump(mode="json")
    # Client-supplied confidence must never turn a manual edit into an OCR fact.
    sources = previous["sources"].copy()
    for field, value in data.items():
        if field in ("sources", "review_reasons"):
            continue
        if value != previous.get(field):
            sources[field] = {"kind": "manual", "state": "READ" if value is not None else "UNREVIEWED",
                              "boxes": previous["sources"].get(field, {}).get("boxes", [])}
    data["sources"] = sources
    scalar_fields = set(DocumentFacts.model_fields) - {"sources", "review_reasons", "discounts", "date_candidates"}
    requested = {field: source["state"] for field, source in incoming.get("sources", {}).items() if field in scalar_fields}
    _manual_states(data, sources, requested, inherited=True)
    return DocumentFacts.model_validate(data).model_dump(mode="json")


def _save_line_items(session: Session, receipt: Receipt, incoming: list[dict], *, project_legacy: bool = True, trusted_ocr: bool = False) -> None:
    existing = {row.id: row for row in session.exec(select(LineItem).where(LineItem.receipt_id == receipt.id)).all()}
    seen, prepared = set(), []
    for position, value in enumerate(incoming):
        item = StructuredItem.model_validate(value)
        if item.id is not None and (item.id not in existing or item.id in seen):
            raise AppException(400, "VALIDATION_ERROR", "품목 ID는 이 영수증의 기존 품목에 중복 없이 연결해야 합니다.")
        item_id = item.id or str(uuid.uuid4())
        seen.add(item_id)
        old = json.loads(existing[item_id].data_json) if item_id in existing else {}
        data = item.model_dump(mode="json")
        data["id"] = item_id
        data["original_name"] = old.get("original_name") or item.original_name or item.name
        data["sources"] = data["sources"].copy() if trusted_ocr else old.get("sources", {}).copy()
        for field, value in data.items():
            if field in ("id", "sources", "original_name", "effective_unit_price"):
                continue
            if value != old.get(field) and not trusted_ocr:
                data["sources"][field] = {"kind": "manual", "state": "READ" if value is not None else "UNREVIEWED",
                                          "boxes": old.get("sources", {}).get(field, {}).get("boxes", [])}
        if not trusted_ocr:
            for field in ("name", "specification", "unit", "quantity", "printed_unit_price", "line_amount", "discount_amount"):
                requested = item.sources.get(field)
                if requested is None:
                    continue
                has_value = data.get(field) is not None and data.get(field) != ""
                previous_state = old.get("sources", {}).get(field, {}).get("state")
                # An unchanged READ source accompanies clearing an old value in legacy clients.
                if requested.state == "READ" and not has_value and previous_state == "READ":
                    continue
                if requested.state == "READ" and not has_value or requested.state in ("ABSENT", "FAILED", "NOT_APPLICABLE") and has_value:
                    raise AppException(400, "VALIDATION_ERROR", "값 상태와 입력값이 맞지 않습니다. 읽은 값에는 값을 입력하세요.")
                if requested.state == previous_state:
                    continue
                data["sources"][field] = {"kind": "manual", "state": requested.state,
                    "boxes": old.get("sources", {}).get(field, {}).get("boxes", [])}
        completed = complete_item(StructuredItem.model_validate(data))
        prepared.append((position, completed))
    for item_id, row in existing.items():
        if item_id not in seen:
            session.delete(row)
    legacy_amounts = []
    for position, item in prepared:
        row = existing.get(item.id) or LineItem(id=item.id, receipt_id=receipt.id, position=position, data_json="{}")
        row.position = position
        row.data_json = item.model_dump_json()
        session.add(row)
        legacy_amounts.append({"item_index": position, "item_name": item.name, "quantity": item.quantity,
                               "unit_price": item.printed_unit_price, "line_amount": item.line_amount,
                               "sources": {k: {"kind": v.kind} for k, v in item.sources.items() if k in ("quantity", "line_amount")}})
    if project_legacy:
        receipt.items_json = json.dumps([item.name for _, item in prepared], ensure_ascii=False)
        receipt.item_amounts_json = json.dumps(legacy_amounts, ensure_ascii=False)
        session.add(receipt)
    session.flush()
    session.expire(receipt, ["line_items"])


def _sync_legacy_items(session: Session, receipt: Receipt) -> None:
    names = json.loads(receipt.items_json or "[]")
    numbers = {row["item_index"]: row for row in json.loads(receipt.item_amounts_json or "[]")}
    existing = session.exec(select(LineItem).where(LineItem.receipt_id == receipt.id).order_by(LineItem.position)).all()
    values = []
    for position, name in enumerate(names):
        # The old input format has no identity; only preserve an unchanged row.
        old = existing[position] if position < len(existing) else None
        old_data = json.loads(old.data_json) if old else {}
        row = numbers.get(position, {})
        values.append({"id": old.id if old and old_data.get("name") == name else None,
                       "name": name, "original_name": name, "quantity": row.get("quantity"),
                       "printed_unit_price": row.get("unit_price") if row.get("sources", {}).get("unit_price", {}).get("kind") != "calculated" else None,
                       "line_amount": row.get("line_amount")})
    _save_line_items(session, receipt, values, project_legacy=False)


def update_ocr(
    session: Session,
    user_id: uuid.UUID,
    receipt_id: int,
    payload: ReceiptOcrUpdate,
) -> ReceiptOut:
    receipt = _owned_receipt(session, user_id, receipt_id)
    checked_revision = receipt.revision
    if payload.base_revision != checked_revision:
        raise AppException(409, "DATA_CONFLICT", "영수증이 바뀌었습니다. 최신 값을 확인하세요.")
    if receipt.confirmed:
        raise AppException(409, "DATA_CONFLICT", "이미 확정된 영수증은 수정할 수 없습니다.")
    data = payload.model_dump(exclude_unset=True)
    data.pop("base_revision")
    field_states = data.pop("field_states", {})
    structured_items = data.pop("line_items", None)
    document = data.pop("document", None)
    if document is not None:
        data["document_json"] = json.dumps(_edited_document(receipt, document), ensure_ascii=False)
    checked_items = receipt.items_json
    checked_item_amounts = receipt.item_amounts_json
    checked_schema_version = receipt.money_schema_version
    base_items = data.pop("base_items", None)
    base_item_amounts = data.pop("base_item_amounts", None)
    if (base_items is not None and base_items != json.loads(checked_items or "[]")) or (
        base_item_amounts is not None and base_item_amounts != json.loads(checked_item_amounts or "[]")
    ):
        raise AppException(409, "DATA_CONFLICT", "품목 값이 바뀌었습니다. 다시 확인하세요.")
    new_item_amounts = data.pop("item_amounts", None)
    base_amount = data.pop("base_amount", None)
    base_supply = data.pop("base_supply_amount", None)
    base_vat = data.pop("base_vat_amount", None)
    has_base = any(
        key in payload.model_fields_set
        for key in ("base_amount", "base_supply_amount", "base_vat_amount")
    )
    bases = {field: data.pop(f"base_{field}") for field in NEW_FIELDS if f"base_{field}" in data}
    if has_base:
        bases.update(amount=base_amount, supply_amount=base_supply, vat_amount=base_vat)
    edited_document = DocumentFacts.model_validate_json(data.get("document_json") or receipt.document_json or "{}")
    _reject_negative_money(data, allow_signed=bool(edited_document.adjustment_type))
    checked = {field: getattr(receipt, field) for field in MONEY_FIELDS}
    sources = json.loads(receipt.money_sources_json or "{}")
    money = dict(checked)
    calculated_fields = {field for field, source in sources.items() if source.get("kind") == "calculated"}
    # 계산 값은 원래 입력이 바뀌면 다시 계산한다. 같은 값을 재전송해도 인쇄 값으로 승격하지 않는다.
    for field, source in list(sources.items()):
        if source.get("kind") == "calculated" and field not in field_states and data.get(field, checked.get(field)) == checked.get(field):
            money[field] = None
            sources.pop(field)
    for field in MONEY_FIELDS:
        if field in data:
            if field in calculated_fields and field not in field_states and data[field] == checked[field]:
                continue
            if data[field] != checked[field] or field not in sources:
                money[field] = data[field]
                if data[field] is None:
                    sources[field] = {"kind": "manual", "state": "UNREVIEWED", "confidence": None,
                                      "boxes": sources.get(field, {}).get("boxes", [])}
                else:
                    sources[field] = {"kind": "manual", "state": "READ", "confidence": None,
                                      "boxes": sources.get(field, {}).get("boxes", [])}
    _manual_states({**money, **data}, sources, {key: state for key, state in field_states.items() if key in MONEY_FIELDS})
    if structured_money({**checked, **data}):
        money, sources = complete_money(money, sources, allow_signed=bool(edited_document.adjustment_type))
        data.update({field: money.get(field) for field in (*NEW_FIELDS, "vat_amount")})
    if any(field in data for field in MONEY_FIELDS) or any(field in field_states for field in MONEY_FIELDS):
        data["money_sources_json"] = json.dumps(sources, ensure_ascii=False)
    facts = {key: data.get(key, getattr(receipt, key)) for key in ("vendor", "date", "business_number")}
    doc_data = edited_document.model_dump(mode="json")
    for key, value in facts.items():
        if key in data and value != getattr(receipt, key):
            doc_data["sources"][key] = {"kind": "manual", "state": "READ" if value is not None and value != "" else "UNREVIEWED",
                "boxes": doc_data["sources"].get(key, {}).get("boxes", []), "confidence": None}
    _manual_states(facts, doc_data["sources"], {key: state for key, state in field_states.items() if key not in MONEY_FIELDS})
    data["document_json"] = DocumentFacts.model_validate(doc_data).model_dump_json()
    values: dict = {}
    values["revision"] = checked_revision + 1
    if receipt.money_schema_version == 2 or any(field in data for field in NEW_FIELDS):
        values["money_schema_version"] = 2
    item_names = data.get("items", json.loads(checked_items or "[]")) or []
    old_rows = json.loads(checked_item_amounts or "[]")
    if new_item_amounts is not None:
        seen = set()
        rows = []
        for row in new_item_amounts:
            index = row["item_index"]
            if index in seen or index >= len(item_names):
                raise AppException(400, "VALIDATION_ERROR", "단가 보완 값은 중복 없이 기존 품목에 연결해야 합니다.")
            seen.add(index)
            previous = next((old for old in old_rows if old["item_index"] == index and old["item_name"] == item_names[index]), {})
            row["item_name"] = item_names[index]
            row["sources"] = {}
            for field in ("quantity", "line_amount", "unit_price"):
                source = previous.get("sources", {}).get(field)
                if field == "unit_price" and source and source.get("kind") == "calculated" and row.get(field) == previous.get(field):
                    row[field] = None
                elif row.get(field) is not None:
                    row["sources"][field] = source if source and row[field] == previous.get(field) else {"kind": "manual"}
            rows.append(complete_unit_price(row))
        values["item_amounts_json"] = json.dumps(rows, ensure_ascii=False) if rows else None
    elif "items" in data:
        # 이름이 바뀐 품목에 예전 수량/단가를 옮기지 않는다.
        rows = [row for row in old_rows if row["item_index"] < len(item_names) and row["item_name"] == item_names[row["item_index"]]]
        values["item_amounts_json"] = json.dumps(rows, ensure_ascii=False) if rows else None
    if "items" in data:
        items = data.pop("items")
        values["items_json"] = json.dumps(items, ensure_ascii=False) if items else None
    values.update(data)
    conditions = [
        Receipt.id == receipt_id,
        Receipt.user_id == user_id,
        Receipt.revision == checked_revision,
        Receipt.confirmed == False,  # noqa: E712
        Receipt.items_json == checked_items,
        Receipt.item_amounts_json == checked_item_amounts,
        Receipt.money_schema_version == checked_schema_version,
    ]
    conditions.extend(getattr(Receipt, field) == value for field, value in bases.items())
    # 계산에 사용한 읽기 값도 같은 UPDATE에서 확인한다.
    conditions.extend(getattr(Receipt, field) == value for field, value in checked.items())
    session.expire(receipt)
    result = session.execute(sa_update(Receipt).where(*conditions).values(**values))
    if result.rowcount != 1:
        current = _owned_receipt(session, user_id, receipt_id)
        if current.confirmed:
            message = "이미 확정된 영수증은 수정할 수 없습니다."
        elif current.items_json != checked_items or current.item_amounts_json != checked_item_amounts:
            message = "품목 값이 바뀌었습니다. 다시 확인하세요."
        elif current.money_schema_version != checked_schema_version or any(getattr(current, field) != value for field, value in checked.items()) or any(
            getattr(current, field) != value for field, value in bases.items()
        ):
            message = "금액이 바뀌었습니다. 다시 확인한 뒤 확정하세요."
        else:
            message = "영수증을 수정하지 못했습니다."
        _rollback_best_effort(session)
        raise AppException(409, "DATA_CONFLICT", message)
    try:
        if structured_items is not None:
            _save_line_items(session, receipt, structured_items)
        elif "items" in payload.model_fields_set or new_item_amounts is not None:
            _sync_legacy_items(session, receipt)
        current_document = DocumentFacts.model_validate_json(receipt.document_json or "{}")
        item_ids = {item.id for item in session.exec(select(LineItem).where(LineItem.receipt_id == receipt.id)).all()}
        if any(not set(discount.item_ids).issubset(item_ids) for discount in current_document.discounts):
            raise AppException(400, "VALIDATION_ERROR", "할인 대상 품목이 이 영수증에 없습니다.")
        from app.receipts.transactions import find_duplicates
        find_duplicates(session, receipt)
    except Exception:
        _rollback_best_effort(session)
        raise
    session.commit()
    updated = _owned_receipt(session, user_id, receipt_id)
    return ReceiptOut.model_validate(updated)


def confirm_receipt(
    session: Session,
    user_id: uuid.UUID,
    receipt_id: int,
    payload: ReceiptConfirmIn,
) -> ReceiptOut:
    receipt = _owned_receipt(session, user_id, receipt_id)
    checked_revision = receipt.revision
    if payload.base_revision != checked_revision:
        raise AppException(409, "DATA_CONFLICT", "영수증이 바뀌었습니다. 최신 값을 확인한 뒤 확정하세요.")
    if not payload.confirmed:
        raise AppException(400, "VALIDATION_ERROR", "확정하려면 confirmed를 true로 보내야 합니다.")
    if receipt.status == "retake":
        raise AppException(
            409,
            "DATA_CONFLICT",
            receipt.quality_reason or "사진 품질이 낮아 다시 찍어야 합니다.",
        )
    total = receipt.transaction_amount if receipt.transaction_amount is not None else receipt.amount
    if not (receipt.vendor and receipt.vendor.strip()) or receipt.date is None or total is None:
        raise AppException(400, "VALIDATION_ERROR", "상호, 거래일, 총액이 있어야 확정할 수 있습니다.")
    checked = {field: getattr(receipt, field) for field in MONEY_FIELDS}
    document = DocumentFacts.model_validate_json(receipt.document_json or "{}")
    money_sources = json.loads(receipt.money_sources_json or "{}")
    required_sources = {key: document.sources.get(key) for key in ("vendor", "date")}
    if any(source is not None and source.state == "UNREVIEWED" for source in required_sources.values()) or any(
        money_sources.get(key, {}).get("state") == "UNREVIEWED"
        for key in ("taxable_supply_amount", "tax_exempt_amount", "vat_amount", "transaction_amount")
    ):
        raise AppException(409, "DATA_CONFLICT", "확정에 필요한 값을 확인한 뒤 값 상태를 읽음으로 변경하세요.")
    _reject_negative_money(checked, allow_signed=bool(document.adjustment_type))
    if document.adjustment_type in ("RETURN", "CANCELLATION") and (total >= 0 or any(
        value is not None and value > 0 for field, value in checked.items() if field != "subtotal_amount")):
        raise AppException(400, "VALIDATION_ERROR", "반품·취소 금액은 음수 부호를 확인하세요.")
    problem = money_problem(checked, required=True)
    if problem:
        raise AppException(409, "DATA_CONFLICT", problem)
    checked_items, checked_item_amounts = receipt.items_json, receipt.item_amounts_json
    checked_schema_version = receipt.money_schema_version
    # Missing printed quantity/price does not invalidate otherwise readable facts.
    checked_vendor, checked_date = receipt.vendor, receipt.date
    session.expire(receipt)
    result = session.execute(
        sa_update(Receipt)
        .where(
            Receipt.id == receipt_id,
            Receipt.user_id == user_id,
            Receipt.revision == checked_revision,
            Receipt.confirmed == False,  # noqa: E712
            Receipt.status != "retake",
            Receipt.vendor == checked_vendor,
            Receipt.date == checked_date,
            Receipt.items_json == checked_items,
            Receipt.item_amounts_json == checked_item_amounts,
            Receipt.money_schema_version == checked_schema_version,
            *(getattr(Receipt, field) == checked[field] for field in MONEY_FIELDS),
        )
        .values(confirmed=True, status="done", revision=checked_revision + 1)
    )
    if result.rowcount != 1:
        current = _owned_receipt(session, user_id, receipt_id)
        if current.items_json != checked_items or current.item_amounts_json != checked_item_amounts:
            message = "품목 값이 바뀌었습니다. 다시 확인하세요."
        elif current.money_schema_version != checked_schema_version or any(getattr(current, field) != checked[field] for field in MONEY_FIELDS):
            message = "금액이 바뀌었습니다. 다시 확인한 뒤 확정하세요."
        elif current.confirmed:
            message = "이미 확정된 영수증입니다."
        else:
            message = "이미 확정되었거나 다시 찍어야 하는 영수증입니다."
        _rollback_best_effort(session)
        raise AppException(409, "DATA_CONFLICT", message)
    try:
        from app.receipts.transactions import create_from_receipt
        if receipt.transaction_id is None:
            create_from_receipt(session, receipt)
        session.commit()
    except Exception:
        _rollback_best_effort(session)
        raise
    updated = _owned_receipt(session, user_id, receipt_id)
    return ReceiptOut.model_validate(updated)


def list_confirmed_receipts(session: Session, user_id: uuid.UUID) -> list[ReceiptOut]:
    statement = (
        select(Receipt)
        .where(Receipt.user_id == user_id, Receipt.confirmed.is_(True))
        .order_by(Receipt.created_at.desc(), Receipt.id.desc())
    )
    return [ReceiptOut.model_validate(item) for item in session.exec(statement).all()]


def _commit_receipt(session: Session, receipt: Receipt) -> ReceiptOut:
    try:
        session.add(receipt)
        session.commit()
        session.refresh(receipt)
        return ReceiptOut.model_validate(receipt)
    except AppException:
        raise
    except Exception as exc:
        _rollback_best_effort(session)
        raise AppException(500, "DATABASE_ERROR", "영수증 저장에 실패했습니다.") from exc
