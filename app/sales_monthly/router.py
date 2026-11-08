import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.common.exceptions import AppException
from app.core.config import settings
from app.core.database import get_session
from app.receipts import service as receipt_service
from app.receipts.ocr.luna_client import LunaFailure
from app.sales_monthly import service, spreadsheet, tax_lines
from app.sales_monthly.models import MonthlySalesDocument

router = APIRouter(prefix='/sales/monthly', tags=['monthly sales'])

def owned(session, user, document_id):
    item = session.exec(select(MonthlySalesDocument).where(MonthlySalesDocument.id == document_id, MonthlySalesDocument.user_id == user.id)).first()
    if item is None:
        raise AppException(404, 'NOT_FOUND', '정산서를 찾을 수 없습니다.')
    return item

def output(item):
    reviewed = json.loads(item.review_json)
    is_spreadsheet = item.contract_version == spreadsheet.VERSION
    warnings = service.prepare_review(reviewed)['warnings']
    if is_spreadsheet:
        warnings += json.loads(item.ocr_json).get("warnings", [])
    return {'id':item.id, 'status':item.status, 'created_at':item.created_at.isoformat(), 'updated_at':item.updated_at.isoformat(), 'deleted_at':item.deleted_at.isoformat() if item.deleted_at else None, 'document':reviewed, 'raw_prediction':json.loads(item.raw_prediction_json), 'warnings':warnings, 'lines':tax_lines.row_lines(reviewed), 'file_type': 'spreadsheet' if is_spreadsheet else 'image'}

def listed(session, user, in_trash):
    deleted = MonthlySalesDocument.deleted_at.is_not(None) if in_trash else MonthlySalesDocument.deleted_at.is_(None)
    rows = session.exec(select(MonthlySalesDocument).where(MonthlySalesDocument.user_id == user.id, deleted).order_by(MonthlySalesDocument.created_at.desc())).all()
    return [output(row) for row in rows]

def set_trashed(session, item, trashed):
    item.deleted_at = datetime.now(timezone.utc) if trashed else None
    item.updated_at = datetime.now(timezone.utc)
    session.add(item); session.commit(); session.refresh(item)
    return output(item)

@router.get('')
def list_documents(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return listed(session, user, in_trash=False)

# 매입 거래와 같은 휴지통: 옮기면 보관함·세액 계산에서 빠지고, 복원하면 돌아온다.
@router.get('/trash')
def list_trash(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return listed(session, user, in_trash=True)

@router.post('/{document_id}/trash')
def move_to_trash(document_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return set_trashed(session, owned(session,user,document_id), True)

@router.post('/{document_id}/restore')
def restore(document_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return set_trashed(session, owned(session,user,document_id), False)

@router.delete('/{document_id}', status_code=204)
def delete_permanently(document_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """휴지통에 있는 정산서와 원본 사진을 지운다. 되돌릴 수 없다."""
    item = owned(session,user,document_id)
    if item.deleted_at is None:
        raise AppException(409, 'DOCUMENT_NOT_IN_TRASH', '영구 삭제 전에 휴지통으로 이동해 주세요.')
    image_key = item.image_key
    session.delete(item); session.commit()
    receipt_service._delete_after_failure(image_key)  # 사진 정리는 best effort
    return Response(status_code=204)

class ReviewInput(BaseModel):
    document: dict[str, Any]

@router.post('/lines')
def preview_lines(payload: ReviewInput, user: User = Depends(get_current_user)):
    """저장하지 않고, 수정 중인 정산서가 세액 계산에 어떻게 들어갈지 계산만 한다."""
    try:
        service.validate_document(payload.document, legacy_allowed=True)
    except (LunaFailure, KeyError, TypeError):
        raise AppException(400,'INVALID_REVIEW','입력한 정산서 항목을 확인해 주세요.') from None
    return tax_lines.summarize(payload.document)

@router.get('/{document_id}')
def get_document(document_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return output(owned(session,user,document_id))

@router.get('/{document_id}/image')
def get_image(document_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    item = owned(session,user,document_id)
    try:
        headers = {'Cache-Control':'private, no-store'}
        if item.contract_version == spreadsheet.VERSION:
            extension = item.image_key.rsplit(".", 1)[-1]
            headers["Content-Disposition"] = f'attachment; filename="sales-original.{extension}"'
        return Response(receipt_service.storage.read(item.image_key), media_type=item.image_mime, headers=headers)
    except OSError:
        raise AppException(404, 'NOT_FOUND', '원본 정산서를 찾을 수 없습니다.') from None

@router.put('/{document_id}/review')
def save_review(document_id: int, payload: ReviewInput, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    item=owned(session,user,document_id)
    document = payload.document
    if '매출증빙' not in document:
        previous = json.loads(item.review_json)
        if '매출증빙' in previous:
            document = {**document, '매출증빙': previous['매출증빙']}
    try:
        if item.contract_version == spreadsheet.VERSION:
            spreadsheet.validate_review(document, json.loads(item.raw_prediction_json))
        else:
            service.validate_document(document, legacy_allowed=True)
    except (LunaFailure, KeyError, TypeError):
        raise AppException(400,'INVALID_REVIEW','입력한 정산서 항목을 확인해 주세요.') from None
    item.review_json=json.dumps(document,ensure_ascii=False)
    item.status='reviewed'
    item.updated_at=datetime.now(timezone.utc)
    session.add(item);session.commit();session.refresh(item)
    return output(item)

@router.post('/spreadsheet', status_code=201)
async def import_spreadsheet(
    file: UploadFile = File(...), source: str = Form(...),
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    data = await file.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
    if not data or len(data) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise spreadsheet.invalid("업로드할 엑셀 파일의 크기를 확인해 주세요.")
    document, warnings, extension = await run_in_threadpool(spreadsheet.read, data, file.filename or "", source)
    digest = hashlib.sha256(data).hexdigest()
    def find_previous():
        return session.exec(select(MonthlySalesDocument).where(
            MonthlySalesDocument.user_id == user.id, MonthlySalesDocument.image_sha256 == digest
        )).first()

    if (previous := find_previous()) is not None:
        return set_trashed(session, previous, False) if previous.deleted_at else output(previous)
    mime = spreadsheet.MIME[extension]
    stored = receipt_service.storage.save(user.id, data, mime, extension)
    try:
        serialized = json.dumps(document, ensure_ascii=False)
        item = MonthlySalesDocument(
            user_id=user.id, image_key=stored.key, image_mime=mime, image_sha256=digest,
            raw_prediction_json=serialized, review_json=serialized,
            ocr_json=json.dumps({"warnings": warnings}, ensure_ascii=False), model_response_json="{}",
            contract_version=spreadsheet.VERSION,
        )
        session.add(item)
        session.commit()
    except Exception as exc:
        session.rollback()
        receipt_service._delete_after_failure(stored.key)
        if isinstance(exc, IntegrityError) and (previous := find_previous()) is not None:
            return output(previous)
        raise
    session.refresh(item)
    return output(item)

@router.post('/extract', status_code=201)
async def extract(file: UploadFile = File(...), user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    data = await file.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
    mime, extension = receipt_service.validate_image(data, file.content_type)
    digest=hashlib.sha256(data).hexdigest()
    # 같은 사진은 다시 인식하지 않고 앞서 읽은 정산서를 그대로 연다(비용·매출 중복 방지).
    find_previous=lambda: session.exec(select(MonthlySalesDocument).where(MonthlySalesDocument.user_id==user.id,MonthlySalesDocument.image_sha256==digest)).first()
    if (previous:=find_previous()) is not None:
        return set_trashed(session, previous, False) if previous.deleted_at else output(previous)  # 휴지통에 있던 사진이면 복원해서 연다
    try:
        result=await service.recognize(data, mime)
    except LunaFailure as exc:
        status = 400 if exc.code in {'INVALID_IMAGE_SIZE','INVALID_IMAGE','UNSUPPORTED_IMAGE'} else 503
        raise AppException(status, exc.code, '매출 정산서를 읽지 못했습니다. 설정과 사진을 확인해 주세요.') from None
    stored=receipt_service.storage.save(user.id,data,mime,extension)
    try:
        item=MonthlySalesDocument(user_id=user.id,image_key=stored.key,image_mime=mime,image_sha256=digest,raw_prediction_json=json.dumps(result['raw_prediction'],ensure_ascii=False),review_json=json.dumps(result['document'],ensure_ascii=False),ocr_json=json.dumps(result['ocr_response'],ensure_ascii=False),model_response_json=json.dumps(result['model_response'],ensure_ascii=False),contract_version=result['contract_version'])
        session.add(item);session.commit();session.refresh(item)
    except Exception as exc:
        session.rollback(); receipt_service._delete_after_failure(stored.key)
        if isinstance(exc,IntegrityError) and (previous:=find_previous()) is not None:
            return output(previous)
        raise
    return output(item)
