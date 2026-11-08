import json,hashlib
from pathlib import Path
from fastapi import APIRouter,Depends
from fastapi.responses import Response
from pydantic import BaseModel,EmailStr
from sqlmodel import Session,select
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.database import get_session
from app.core.config import settings
from app.common.exceptions import AppException
from app.receipts.storage import LocalFileStorage
from app.team_benchmark.models import TeamMember,BenchmarkCase
router=APIRouter(prefix='/v2/team-benchmark',tags=['team-benchmark'])

def member(user:User=Depends(get_current_user),db:Session=Depends(get_session)):
    m=db.get(TeamMember,user.id)
    if not m or not m.enabled:raise AppException(403,'TEAM_ACCESS_DENIED','승인된 팀원만 볼 수 있습니다.')
    return m

def maintainer(m:TeamMember=Depends(member)):
    if m.role!='maintainer':raise AppException(403,'TEAM_ADMIN_REQUIRED','팀 자료 관리 권한이 필요합니다.')
    return m

@router.get('/access')
def access(user:User=Depends(get_current_user),db:Session=Depends(get_session)):
    m=db.get(TeamMember,user.id)
    return {'allowed':bool(m and m.enabled),'can_manage':bool(m and m.enabled and m.role=='maintainer')}

@router.get('/members')
def members(m:TeamMember=Depends(maintainer),db:Session=Depends(get_session)):
    return [{'email':u.email,'name':u.name,'role':t.role,'enabled':t.enabled} for t,u in db.exec(select(TeamMember,User).where(TeamMember.user_id==User.id)).all()]

class MemberUpdate(BaseModel):
    email:EmailStr
    enabled:bool=True

@router.put('/members')
def update_member(body:MemberUpdate,m:TeamMember=Depends(maintainer),db:Session=Depends(get_session)):
    u=db.exec(select(User).where(User.email==str(body.email))).first()
    if not u:raise AppException(404,'USER_NOT_FOUND','먼저 서비스에 가입한 계정을 입력해 주세요.')
    old=db.get(TeamMember,u.id)
    if old and old.role=='maintainer':raise AppException(409,'MAINTAINER_PROTECTED','관리 계정 권한은 이 화면에서 변경할 수 없습니다.')
    old=old or TeamMember(user_id=u.id)
    old.enabled=body.enabled;db.add(old);db.commit();return {'email':u.email,'enabled':old.enabled}

@router.get('/cases')
def cases(m:TeamMember=Depends(member),db:Session=Depends(get_session)):
    return [{'case_id':c.case_id,'category':c.category,'tags':json.loads(c.tags_json)} for c in db.exec(select(BenchmarkCase).order_by(BenchmarkCase.case_id)).all()]

@router.get('/cases/{case_id}')
def detail(case_id:str,m:TeamMember=Depends(member),db:Session=Depends(get_session)):
    c=db.get(BenchmarkCase,case_id)
    if not c:raise AppException(404,'NOT_FOUND','자료를 찾을 수 없습니다.')
    return {'case_id':c.case_id,'category':c.category,'tags':json.loads(c.tags_json),'gold':json.loads(c.gold_json),'prediction':json.loads(c.prediction_json),'metadata':json.loads(c.metadata_json)}

@router.get('/cases/{case_id}/image')
def picture(case_id:str,m:TeamMember=Depends(member),db:Session=Depends(get_session)):
    c=db.get(BenchmarkCase,case_id)
    if not c:raise AppException(404,'NOT_FOUND','자료를 찾을 수 없습니다.')
    try:data=LocalFileStorage(settings.STORAGE_DIR).read(c.image_key)
    except OSError:raise AppException(503,'IMAGE_UNAVAILABLE','사진 파일을 확인해 주세요.')
    if hashlib.sha256(data).hexdigest()!=c.image_sha256:raise AppException(503,'IMAGE_INTEGRITY_ERROR','사진 파일 검증에 실패했습니다.')
    return Response(data,media_type=json.loads(c.metadata_json).get('image_mime','image/png'),headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
