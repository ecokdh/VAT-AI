from datetime import date
import httpx
import pytest
from sqlmodel import select
from app.auth import service as auth_service
from app.auth.models import User
from app.business.models import BusinessProfile
from app.business.schemas import BusinessVerifyResponse
from app.business import nts_client
from app.business.nts_client import validate_identity as real_validate_identity
from app.common.exceptions import AppException
from app.core.config import settings
from app.core.database import get_session
from app.main import app


@pytest.fixture
def registration(monkeypatch):
    monkeypatch.setattr(auth_service, 'verify_business', lambda _: BusinessVerifyResponse(
        business_number='1234567890', business_status='계속사업자', business_status_code='01',
        tax_type='일반과세', tax_type_code='01', verified=True))
    return dict(email='qa-polish@example.com', password='Test-pass-123!', name='실제 대표자', nickname='  별빛상점  ',
                business_name='고정 상호', business_number='1234567890', terms_accepted=True,
                privacy_accepted=True, tax_profile={'business_start_date':'2025-01-01'})


def test_nickname_is_separate_and_only_owner_can_update(client, registration):
    reg=client.post('/auth/register', json=registration)
    assert reg.status_code==201, reg.text
    assert reg.json()['user']['nickname']=='별빛상점'
    headers={'Authorization':'Bearer '+reg.json()['access_token']}
    result=client.patch('/auth/me', headers=headers, json={'nickname':'  새이름  '})
    assert result.status_code==200
    assert result.json()['nickname']=='새이름' and result.json()['name']=='실제 대표자'
    assert client.patch('/auth/me', json={'nickname':'침입자'}).status_code==401
    for body in ({'nickname':' '},{'nickname':'가'*21},{'nickname':'정상','name':'변경 시도'}):
        assert client.patch('/auth/me', headers=headers, json=body).status_code==400
    assert client.get('/auth/me', headers=headers).json()['nickname']=='새이름'
    other=client.post('/auth/register', json={**registration,'email':'other@example.com','nickname':'다른계정'}).json()
    assert client.get('/auth/me', headers={'Authorization':'Bearer '+other['access_token']}).json()['nickname']=='다른계정'


def test_business_name_change_rejected_without_profile_side_effects(client, registration):
    reg=client.post('/auth/register',json=registration).json()
    headers={'Authorization':'Bearer '+reg['access_token']}
    before=client.get('/v2/business/profile',headers=headers).json()
    result=client.put('/v2/business/profile',headers=headers,json={'business_name':'새상호','has_employees':True})
    assert result.status_code==400 and result.json()['error']['code']=='BUSINESS_NAME_IMMUTABLE'
    assert client.get('/v2/business/profile',headers=headers).json()==before


def test_registration_verifies_identity_on_server_and_rolls_back(client, registration, monkeypatch):
    seen=[]
    def mismatch(number,name,start):
        seen.append((number,name,start))
        raise AppException(400,'BUSINESS_IDENTITY_MISMATCH','불일치')
    monkeypatch.setattr(auth_service,'verify_identity',mismatch)
    response=client.post('/auth/register',json=registration)
    assert response.status_code==400 and response.json()['error']['code']=='BUSINESS_IDENTITY_MISMATCH'
    assert seen==[('1234567890','실제 대표자',date(2025,1,1))]
    gen=app.dependency_overrides[get_session](); session=next(gen)
    try:
        assert session.exec(select(User)).all()==[]
        assert session.exec(select(BusinessProfile)).all()==[]
    finally:gen.close()


def test_registration_requires_date_and_valid_nickname(client, registration):
    assert client.post('/auth/register',json={**registration,'tax_profile':None}).json()['error']['code']=='BUSINESS_START_DATE_REQUIRED'
    assert client.post('/auth/register',json={**registration,'nickname':'  '}).status_code==400


@pytest.mark.parametrize('valid,expected',[('01',None),('02','BUSINESS_IDENTITY_MISMATCH'),('99','BUSINESS_API_INVALID_RESPONSE')])
def test_nts_identity_contract(monkeypatch, valid, expected):
    monkeypatch.setattr(settings,'NTS_BUSINESS_API_KEY','test-key')
    def post(url, **kwargs):
        assert url==settings.NTS_BUSINESS_VALIDATE_URL
        assert kwargs['json']=={'businesses':[{'b_no':'1234567890','start_dt':'20250101','p_nm':'대표자'}]}
        return httpx.Response(200,json={'status_code':'OK','data':[{'b_no':'1234567890','valid':valid}]})
    monkeypatch.setattr(nts_client.httpx,'post',post)
    if expected:
        with pytest.raises(AppException) as exc:real_validate_identity('1234567890','대표자','20250101')
        assert exc.value.code==expected
    else:real_validate_identity('1234567890','대표자','20250101')
