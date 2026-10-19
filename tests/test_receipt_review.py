import copy,json
from datetime import date
import pytest
from pydantic import ValidationError
from sqlmodel import Session,SQLModel,create_engine
from app.auth.models import User
from app.jobs.service import confirm_receipt_extraction
from app.receipts.models import Receipt
from app.receipts.schemas import ExtractionConfirmation,ReceiptOut
from app.transactions.models import Transaction
from app.common.exceptions import AppException

def document():
    return {'fields':{'vendor':'수정 상점','branch':'수정 지점','business_number':'123-45-67890','transaction_datetime':'2026-10-13 12:30:45','payment_amount':11000,'supply_amount':10000,'vat_amount':1000},'items':[{'name':'수정 상품','source_row':None,'quantity':2,'unit_price':5000,'line_amount':10000,'row_type':'item','parent_row':None},{'name':'쿠폰','source_row':None,'quantity':None,'unit_price':None,'line_amount':-1000,'row_type':'discount','parent_row':0}]}

def payload():return {'vendor':'수정 상점','amount':11000,'date':'2026-10-13','document':document(),'purpose':'매장 운영용 물품 구매','evidence_type':'card_receipt','business_related':True,'tax_treatment':'standard'}

def fixture_db():
    engine=create_engine('sqlite://');SQLModel.metadata.create_all(engine);s=Session(engine)
    user=User(email='review@example.com',name='검증',password_hash='fixture');s.add(user);s.flush()
    original={'engine':'luna_low','image_sha256':'unchanged','document':{'fields':{'vendor':'인식 상점','vat_amount':999},'items':[],'conflicts':['vat_amount'],'uncertain':[]}}
    r=Receipt(user_id=user.id,image_url='original.png',status='done',ocr_raw=json.dumps(original,ensure_ascii=False));s.add(r);s.commit();s.refresh(r)
    return s,user,r,original

def test_full_review_preserves_original_and_persists_all_edits():
    s,user,r,original=fixture_db()
    try:
        saved=confirm_receipt_extraction(s,user.id,r.id,ExtractionConfirmation.model_validate(payload()))
        s.expire_all();loaded=s.get(Receipt,r.id);raw=json.loads(loaded.ocr_raw)
        assert raw['document']==original['document'] and raw['image_sha256']=='unchanged'
        assert raw['review']['document']['fields']['vat_amount']==1000
        assert raw['review']['document']['items'][1]['line_amount']==-1000
        assert raw['review']['purpose']=='매장 운영용 물품 구매'
        assert raw['review']['evidence_type']=='card_receipt' and raw['review']['business_related'] is True
        assert raw['review']['field_sources']['vat_amount']=='user_edit'
        response=ReceiptOut.model_validate(loaded).model_dump()
        assert response['recognition']['document']['fields']['vendor']=='수정 상점'
        assert response['recognition']['original_document']['fields']['vendor']=='인식 상점'
        assert response['review']['purpose']=='매장 운영용 물품 구매'
        assert saved.extraction_confirmed and saved.vendor=='수정 상점' and saved.amount==11000
    finally:s.close()

def test_blank_values_stay_null():
    s,user,r,_=fixture_db();p=payload();p['document']['fields']['vat_amount']=None;p['document']['items'][0]['quantity']=None;p['purpose']=None
    try:
        result=confirm_receipt_extraction(s,user.id,r.id,ExtractionConfirmation.model_validate(p));review=json.loads(result.ocr_raw)['review']
        assert review['document']['fields']['vat_amount'] is None and review['document']['items'][0]['quantity'] is None
        assert review['purpose'] is None
    finally:s.close()

@pytest.mark.parametrize('change',[lambda p:p['document']['items'][1].update(parent_row=1),lambda p:p['document']['items'][1].update(parent_row=9),lambda p:p['document']['fields'].update(vendor='別 상점'),lambda p:p['document']['fields'].update(payment_amount=9999),lambda p:p['document']['fields'].update(vat_amount=float('nan')),lambda p:p['document']['fields'].update(transaction_datetime='2026-10-12 12:00:00')])
def test_invalid_review_rejected(change):
    p=payload();change(p)
    with pytest.raises(ValidationError):ExtractionConfirmation.model_validate(p)

def test_other_account_cannot_edit():
    s,user,r,_=fixture_db();other=User(email='other@example.com',name='other',password_hash='fixture');s.add(other);s.commit()
    try:
        with pytest.raises(AppException):confirm_receipt_extraction(s,other.id,r.id,ExtractionConfirmation.model_validate(payload()))
        assert not s.get(Receipt,r.id).extraction_confirmed
    finally:s.close()

def test_registered_transaction_requires_transaction_editor():
    s,user,r,_=fixture_db();s.add(Transaction(user_id=user.id,receipt_id=r.id,direction='purchase',vendor='old',transaction_date=date(2026,10,13),total_amount=11000));s.commit()
    try:
        with pytest.raises(AppException):confirm_receipt_extraction(s,user.id,r.id,ExtractionConfirmation.model_validate(payload()))
    finally:s.close()

def test_http_edit_reload_and_original_preservation(client):
    from app.main import app
    from app.core.database import get_session
    from app.core.security import create_access_token
    generator=app.dependency_overrides[get_session]();s=next(generator)
    try:
        u=User(email='http-review@example.com',name='검증',password_hash='fixture');s.add(u);s.flush()
        original={'engine':'luna_low','document':{'fields':{'vendor':'원본 상점','vat_amount':999},'items':[],'conflicts':[],'uncertain':[]}}
        r=Receipt(user_id=u.id,image_url='test.png',status='done',ocr_raw=json.dumps(original));s.add(r);s.commit();s.refresh(r)
        headers={'Authorization':'Bearer '+create_access_token(u.id,u.email)}
        response=client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=headers,json=payload())
        assert response.status_code==200,response.text
        readback=client.get(f'/v2/receipts/{r.id}',headers=headers).json()
        assert readback['review']['purpose']=='매장 운영용 물품 구매'
        assert readback['recognition']['document']['fields']['vat_amount']==1000
        assert readback['recognition']['original_document']==original['document']
        assert readback['review']['document']['items'][1]['parent_row']==0
        bad=payload();bad['document']['items'][1]['parent_row']=9
        invalid_response=client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=headers,json=bad)
        assert invalid_response.status_code==400
        assert client.get(f'/v2/receipts/{r.id}',headers=headers).json()['review']['document']['items'][1]['parent_row']==0
    finally:generator.close()

def test_raw_name_and_discount_sign_preserved_across_review_and_reload(client):
    from app.main import app
    from app.core.database import get_session
    from app.core.security import create_access_token
    from app.receipts.luna_low_contract import normalize
    generator=app.dependency_overrides[get_session]();s=next(generator)
    try:
        u=User(email='raw-name-review@example.com',name='검증',password_hash='fixture');s.add(u);s.flush()
        raw_pred={
            'h':{'vendor':'스타벅스','branch':None,'business_number':'201-81-21515','datetime':'2026-10-13 12:30:45'},
            'm':[{'role':'payment','scope':'unknown','label':'결제금액','value':11000},{'role':'discount','scope':'unknown','label':'Discount','value':1470}],
            'i':[
                {'n':'아메리카노(120g×2)','q':1,'u':4500,'p':4500,'t':'item','parent':None},
                {'n':'L-WARMING','q':1,'u':None,'p':0,'t':'option','parent':0},
                {'n':'할인쿠폰','q':None,'u':None,'p':1470,'t':'discount','parent':0},
            ],
            'uncertain':[],
        }
        norm_doc=normalize(raw_pred)
        assert norm_doc['items'][0]['name']=='아메리카노(120gx2)' and norm_doc['items'][0]['raw_name']=='아메리카노(120g×2)'
        assert norm_doc['items'][1]['name']=='└WARMING' and norm_doc['items'][1]['raw_name']=='L-WARMING'
        assert norm_doc['items'][2]['line_amount']==1470 and norm_doc['items'][2]['raw_name']=='할인쿠폰'

        original={'engine':'luna_low','document':norm_doc,'confirmed':False}
        r=Receipt(user_id=u.id,image_url='test.png',status='done',ocr_raw=json.dumps(original,ensure_ascii=False));s.add(r);s.commit();s.refresh(r)
        headers={'Authorization':'Bearer '+create_access_token(u.id,u.email)}

        initial_get=client.get(f'/v2/receipts/{r.id}',headers=headers).json()
        loaded_items=initial_get['recognition']['document']['items']
        assert loaded_items[1]['name']=='└WARMING' and loaded_items[1]['raw_name']=='L-WARMING'

        # Simulate ReceiptReviewEditor: user edits display name of option row and adds a new item row (source_row: None, raw_name: None)
        edited_items=copy.deepcopy(loaded_items)
        for idx,it in enumerate(edited_items):
            it['source_row']=idx
        edited_items[1]['name']='따뜻하게 데움'
        edited_items.append({'name':'사용자 직접 추가 품목','raw_name':None,'source_row':None,'quantity':1,'unit_price':1000,'line_amount':1000,'row_type':'item','parent_row':None})

        confirm_body={
            'vendor':'스타벅스',
            'amount':11000,
            'date':'2026-10-13',
            'document':{
                'fields':{
                    'vendor':'스타벅스','branch':None,'business_number':'201-81-21515','transaction_datetime':'2026-10-13 12:30:45',
                    'payment_amount':11000,'supply_amount':10000,'vat_amount':1000,'discount_amount':1470,
                },
                'items':edited_items,
            },
            'purpose':'회의 음료','evidence_type':'card_receipt','business_related':True,'tax_treatment':'standard',
        }
        resp=client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=headers,json=confirm_body)
        assert resp.status_code==200,resp.text

        reloaded=client.get(f'/v2/receipts/{r.id}',headers=headers).json()
        rev_items=reloaded['recognition']['document']['items']
        orig_items=reloaded['recognition']['original_document']['items']
        assert rev_items[0]['name']=='아메리카노(120gx2)' and rev_items[0]['raw_name']=='아메리카노(120g×2)' and rev_items[0]['source_row']==0
        assert rev_items[1]['name']=='따뜻하게 데움' and rev_items[1]['raw_name']=='L-WARMING' and rev_items[1]['source_row']==1
        assert rev_items[2]['line_amount']==1470 and rev_items[2]['raw_name']=='할인쿠폰' and rev_items[2]['source_row']==2
        assert rev_items[3]['name']=='사용자 직접 추가 품목' and rev_items[3]['raw_name'] is None and rev_items[3]['source_row'] is None
        assert orig_items[1]['name']=='└WARMING' and orig_items[1]['raw_name']=='L-WARMING'
    finally:generator.close()

def test_server_enforces_immutable_raw_name_against_client_tampering(client):
    from app.main import app
    from app.core.database import get_session
    from app.core.security import create_access_token
    from app.receipts.luna_low_contract import normalize
    generator=app.dependency_overrides[get_session]();s=next(generator)
    try:
        u=User(email='tamper-raw-name@example.com',name='검증',password_hash='fixture');s.add(u);s.flush()
        raw_pred={
            'h':{'vendor':'스타벅스','branch':None,'business_number':'201-81-21515','datetime':'2026-10-13 12:30:45'},
            'm':[{'role':'payment','scope':'unknown','label':'결제금액','value':11000}],
            'i':[
                {'n':'아메리카노(120g×2)','q':1,'u':4500,'p':4500,'t':'item','parent':None},
                {'n':'L-WARMING','q':1,'u':None,'p':0,'t':'option','parent':0},
            ],
            'uncertain':[],
        }
        original={'engine':'luna_low','document':normalize(raw_pred),'confirmed':False}
        r=Receipt(user_id=u.id,image_url='test.png',status='done',ocr_raw=json.dumps(original,ensure_ascii=False));s.add(r);s.commit();s.refresh(r)
        headers={'Authorization':'Bearer '+create_access_token(u.id,u.email)}

        # 1. Client tries to erase raw_name (None) on item 0, tamper raw_name on item 1, and inject fake raw_name on a user-added item
        tampered_body={
            'vendor':'스타벅스',
            'amount':11000,
            'date':'2026-10-13',
            'document':{
                'fields':{'vendor':'스타벅스','transaction_datetime':'2026-10-13 12:30:45','payment_amount':11000},
                'items':[
                    {'name':'아메리카노 수정','raw_name':None,'source_row':0,'quantity':1,'unit_price':4500,'line_amount':4500,'row_type':'item','parent_row':None},
                    {'name':'데움 옵션 수정','raw_name':'클라이언트임의변조','source_row':1,'quantity':1,'unit_price':None,'line_amount':0,'row_type':'option','parent_row':0},
                    {'name':'신규 추가 행','raw_name':'위조된원출력','source_row':None,'quantity':1,'unit_price':1000,'line_amount':1000,'row_type':'item','parent_row':None},
                ],
            },
        }
        resp=client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=headers,json=tampered_body)
        assert resp.status_code==200,resp.text
        reloaded=client.get(f'/v2/receipts/{r.id}',headers=headers).json()
        items=reloaded['recognition']['document']['items']
        assert items[0]['name']=='아메리카노 수정' and items[0]['raw_name']=='아메리카노(120g×2)'
        assert items[1]['name']=='데움 옵션 수정' and items[1]['raw_name']=='L-WARMING'
        assert items[2]['name']=='신규 추가 행' and items[2]['raw_name'] is None

        # 2. Even if client omits source_row completely and tampers/erases raw_name, server binds to original items
        omitted_source_body=copy.deepcopy(tampered_body)
        omitted_source_body['document']['items']=[
            {'name':'이름완전변경0','raw_name':'조작0','quantity':1,'unit_price':4500,'line_amount':4500,'row_type':'item','parent_row':None},
            {'name':'이름완전변경1','raw_name':None,'quantity':1,'unit_price':None,'line_amount':0,'row_type':'option','parent_row':0},
        ]
        resp2=client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=headers,json=omitted_source_body)
        assert resp2.status_code==400,resp2.text
        assert resp2.json()['error']['code']=='SOURCE_REFERENCE_REQUIRED'
        items2=client.get(f'/v2/receipts/{r.id}',headers=headers).json()['recognition']['document']['items']
        assert items2[0]['raw_name']=='아메리카노(120g×2)'
        assert items2[0]['name']=='아메리카노 수정'
        assert items2[1]['raw_name']=='L-WARMING'

        # 3. Invalid or duplicate source_row is rejected with 400
        bad_source_body=copy.deepcopy(tampered_body)
        bad_source_body['document']['items'][0]['source_row']=99
        assert client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=headers,json=bad_source_body).status_code==400
        dup_source_body=copy.deepcopy(tampered_body)
        dup_source_body['document']['items'][1]['source_row']=0
        assert client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=headers,json=dup_source_body).status_code==400
    finally:generator.close()
