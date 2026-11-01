import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, File, UploadFile
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
from app.receipts.luna_client import LunaFailure, validate
from app.sales_monthly import service
from app.sales_monthly.models import MonthlySalesDocument

router = APIRouter(prefix='/sales/monthly', tags=['monthly sales'])

def owned(session, user, document_id):
    item = session.exec(select(MonthlySalesDocument).where(MonthlySalesDocument.id == document_id, MonthlySalesDocument.user_id == user.id)).first()
    if item is None:
        raise AppException(404, 'NOT_FOUND', '정산서를 찾을 수 없습니다.')
    return item

def output(item):
    reviewed = json.loads(item.review_json)
    return {'id':item.id, 'status':item.status, 'created_at':item.created_at.isoformat(), 'updated_at':item.updated_at.isoformat(), 'document':reviewed, 'raw_prediction':json.loads(item.raw_prediction_json), 'warnings':service.prepare_review(reviewed)['warnings']}

@router.get('')
def list_documents(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(MonthlySalesDocument).where(MonthlySalesDocument.user_id == user.id).order_by(MonthlySalesDocument.created_at.desc())).all()
    return [output(row) for row in rows]

@router.get('/{document_id}')
def get_document(document_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return output(owned(session,user,document_id))

@router.get('/{document_id}/image')
def get_image(document_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    item = owned(session,user,document_id)
    try:
        return Response(receipt_service.storage.read(item.image_key), media_type=item.image_mime, headers={'Cache-Control':'private, no-store'})
    except OSError:
        raise AppException(404, 'NOT_FOUND', '원본 정산서를 찾을 수 없습니다.') from None

class ReviewInput(BaseModel):
    document: dict[str, Any]

@router.put('/{document_id}/review')
def save_review(document_id: int, payload: ReviewInput, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    item=owned(session,user,document_id)
    try:
        validate(payload.document,service.SCHEMA)
    except (LunaFailure, KeyError, TypeError):
        raise AppException(400,'INVALID_REVIEW','입력한 정산서 항목을 확인해 주세요.') from None
    item.review_json=json.dumps(payload.document,ensure_ascii=False)
    item.status='reviewed'
    item.updated_at=datetime.now(timezone.utc)
    session.add(item);session.commit();session.refresh(item)
    return output(item)

@router.post('/extract', status_code=201)
async def extract(file: UploadFile = File(...), user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    data = await file.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
    mime, extension = receipt_service.validate_image(data, file.content_type)
    digest=hashlib.sha256(data).hexdigest()
    previous=session.exec(select(MonthlySalesDocument).where(MonthlySalesDocument.user_id==user.id,MonthlySalesDocument.image_sha256==digest)).first()
    if previous is not None:
        raise AppException(409,'DUPLICATE_DOCUMENT','이미 등록된 사진입니다. 저장된 정산서를 확인해 주세요.')
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
        if isinstance(exc,IntegrityError):
            raise AppException(409,'DUPLICATE_DOCUMENT','이미 등록된 사진입니다.') from None
        raise
    return output(item)
