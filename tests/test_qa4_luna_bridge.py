import json
from app.receipts.details import project_luna_details
from app.receipts.schemas import ReceiptDetails

def test_signed_luna_rows_are_preserved_outside_qa4_compatibility_view():
    doc={'fields':{'business_number':'123-45-67890','supply_amount':10000,'vat_amount':1000,'tax_exempt_amount':None},'items':[
        {'name':'상품','row_type':'item','quantity':1,'unit_price':11000,'line_amount':11000},
        {'name':'쿠폰','row_type':'discount','quantity':None,'unit_price':None,'line_amount':-1000,'parent_row':0}]}
    before=json.dumps(doc,sort_keys=True)
    result=project_luna_details(doc,{'address':'원본 주소','approval_number':'ABC','additional_fields':[{'label':'기타','value':'내용'}]})
    assert ReceiptDetails.model_validate(result).supply_amount==10000
    assert result['address']=='원본 주소' and result['approval_number']=='ABC'
    assert result['items']==[{'name':'상품','quantity':1,'unit_price':11000,'amount':11000}]
    assert json.dumps(doc,sort_keys=True)==before and doc['items'][1]['line_amount']==-1000

def test_qa4_extra_details_and_luna_review_save_together(client):
    from app.main import app
    from app.core.database import get_session
    from app.auth.models import User
    from app.core.security import create_access_token
    from app.receipts.models import Receipt
    gen=app.dependency_overrides[get_session]();s=next(gen)
    try:
        u=User(email='qa4-luna@example.com',name='검증',password_hash='fixture');s.add(u);s.flush()
        doc={'fields':{'vendor':'상점','payment_amount':11000,'supply_amount':10000,'vat_amount':1000,'transaction_datetime':'2026-10-14'},'items':[{'name':'상품','raw_name':'상품','row_type':'item','quantity':1,'unit_price':11000,'line_amount':11000,'parent_row':None}],'conflicts':[],'uncertain':[]}
        r=Receipt(user_id=u.id,image_url='test.png',status='done',ocr_raw=json.dumps({'engine':'luna_low','document':doc},ensure_ascii=False),details_json=json.dumps({'address':'이전 주소'}));s.add(r);s.commit();s.refresh(r)
        h={'Authorization':'Bearer '+create_access_token(u.id,u.email)}
        body={'vendor':'상점','amount':11000,'date':'2026-10-14','document':{'fields':doc['fields'],'items':[{**doc['items'][0],'source_row':0}]},'details':{'address':'수정 주소','phone':'02-123-4567','approval_number':'ABC','additional_fields':[{'label':'기타 표기','value':'인쇄 원문'}]},'question_answers':{'use':'business'}}
        saved=client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=h,json=body)
        assert saved.status_code==200,saved.text
        read=client.get(f'/v2/receipts/{r.id}',headers=h).json()
        assert read['details']['address']=='수정 주소' and read['details']['phone']=='02-123-4567'
        assert read['details']['supply_amount']==10000 and read['details']['items'][0]['amount']==11000
        assert read['recognition']['original_details']['address']=='이전 주소'
        assert read['recognition']['original_document']==doc
        assert read['review']['question_answers']=={'use':'business'}
        assert read['details']['additional_fields']==body['details']['additional_fields']
    finally:gen.close()
