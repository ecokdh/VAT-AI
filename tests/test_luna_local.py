import asyncio,copy,json
import pytest
from app.core.config import settings
from app.receipts import ocr_client,luna_client
from app.receipts.luna_low_contract import normalize

def sample():
    return {'h':{'vendor':'검토상점','branch':None,'business_number':None,'datetime':'2026-10-12 12:30:00'},'m':[{'role':'payment','scope':'unknown','label':'카드 결제','value':11000}],'i':[{'n':'상품','q':None,'u':None,'p':11000,'t':'item','parent':None}],'uncertain':[]}

def test_nulls_not_computed():
    p=luna_client.checked_normalize(sample())
    assert p['fields']['supply_amount'] is None and p['fields']['vat_amount'] is None
    assert p['items'][0]['quantity'] is None and p['items'][0]['unit_price'] is None

@pytest.mark.parametrize('change',[lambda r:r['i'][0].update(parent=0),lambda r:r['i'][0].update(parent=9),lambda r:r['m'][0].update(value='11000'),lambda r:r['i'][0].update(q=True)])
def test_invalid_contract_rejected(change):
    r=sample();change(r)
    with pytest.raises(luna_client.LunaFailure):luna_client.checked_normalize(r)

def test_conflict_preserved():
    r=sample();r['m'].append({'role':'payment','scope':'unknown','label':'현금 결제','value':1000})
    p=luna_client.checked_normalize(r)
    assert p['fields']['payment_amount'] is None and 'payment_amount' in p['conflicts']

def test_luna_dispatch_no_fallback(monkeypatch):
    monkeypatch.setattr(settings,'RECEIPT_RECOGNITION_BACKEND','luna_low')
    async def recognized(*args):return {'engine':'luna_low','document':normalize(sample()),'confirmed':False}
    monkeypatch.setattr(luna_client,'recognize',recognized)
    monkeypatch.setattr(ocr_client,'_extract_fallback',lambda *a:pytest.fail('Unexpected OCR fallback'))
    result=asyncio.run(ocr_client.extract_receipt(b'image','image/png'))
    assert result.engine=='luna_low' and result.amount==11000 and result.date.isoformat()=='2026-10-12'

def test_luna_failure_sanitized(monkeypatch):
    monkeypatch.setattr(settings,'RECEIPT_RECOGNITION_BACKEND','luna_low')
    async def failed(*args):raise luna_client.LunaFailure('MODEL_HTTP_401')
    monkeypatch.setattr(luna_client,'recognize',failed)
    result=asyncio.run(ocr_client.extract_receipt(b'image','image/png'))
    assert result.amount is None and json.loads(result.ocr_raw)['error_code']=='MODEL_HTTP_401'

def test_busy_lock_no_call(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'OPENAI_API_KEY','test-secret')
    monkeypatch.setattr(settings,'LUNA_BUDGET_LEDGER_FILE',str(tmp_path/'budget.json'))
    (tmp_path/'budget.lock').write_text('busy')
    with pytest.raises(luna_client.LunaFailure,match='RECOGNITION_BUSY'):asyncio.run(luna_client.recognize(b'image','image/png'))

def test_usage_reasoning_not_double_counted():
    assert luna_client.usage_cost({'input_tokens':1000,'output_tokens':1000,'output_tokens_details':{'reasoning_tokens':500}})==pytest.approx(1.32)

def test_budget_exceeded_before_generation(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'OPENAI_API_KEY','test-secret')
    monkeypatch.setattr(settings,'LUNA_BUDGET_LEDGER_FILE',str(tmp_path/'budget.json'))
    monkeypatch.setattr(settings,'LUNA_BUDGET_KRW',0)
    calls={'count':0,'generation':0}
    class CountOnly:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,**kwargs):
            if url.endswith('/input_tokens'):
                calls['count']+=1
                return luna_client.httpx.Response(200,json={'input_tokens':1000})
            calls['generation']+=1
            pytest.fail('Model generation endpoint must not be called when budget is insufficient')
    monkeypatch.setattr(luna_client.httpx,'AsyncClient',CountOnly)
    with pytest.raises(luna_client.LunaFailure,match='BUDGET_EXCEEDED'):asyncio.run(luna_client.recognize(b'image','image/png'))
    assert calls['count']==1 and calls['generation']==0
    assert not (tmp_path/'budget.lock').exists()

def test_unconfirmed_reservation_preserved_on_failure_and_timeout(monkeypatch,tmp_path):
    ledger_file=tmp_path/'budget.json'
    monkeypatch.setattr(settings,'OPENAI_API_KEY','test-secret')
    monkeypatch.setattr(settings,'LUNA_BUDGET_LEDGER_FILE',str(ledger_file))
    # Reserve for 1000 input tokens is ((1000*1.2+1024)*0.125+6000*0.5)/1e6*2200 = 7.2116 KRW.
    # Set budget to 10.0 KRW so 1st attempt reserves ~7.21 KRW, fails during generation, and 2nd attempt is blocked with 0 generation calls.
    monkeypatch.setattr(settings,'LUNA_BUDGET_KRW',10.0)
    calls={'count':0,'generation':0}
    class FailOnGeneration:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,**kwargs):
            if url.endswith('/input_tokens'):
                calls['count']+=1
                return luna_client.httpx.Response(200,json={'input_tokens':1000})
            calls['generation']+=1
            raise luna_client.httpx.ReadTimeout('Simulated generation timeout')
    monkeypatch.setattr(luna_client.httpx,'AsyncClient',FailOnGeneration)
    with pytest.raises(luna_client.LunaFailure,match='NETWORK_ERROR'):
        asyncio.run(luna_client.recognize(b'image','image/png'))
    assert calls['generation']==1
    saved_ledger=json.loads(ledger_file.read_text(encoding='utf-8'))
    assert len(saved_ledger['attempts'])==1
    assert saved_ledger['attempts'][0]['status']=='reserved'
    assert 'cost_krw' not in saved_ledger['attempts'][0]
    assert saved_ledger['attempts'][0]['reserved_krw']>7.0

    # Second call sees the unconfirmed reservation (~7.21 KRW) and refuses before calling generation
    with pytest.raises(luna_client.LunaFailure,match='BUDGET_EXCEEDED'):
        asyncio.run(luna_client.recognize(b'image','image/png'))
    assert calls['generation']==1

def test_reservation_exceeded_recorded_when_actual_cost_exceeds_reserve(monkeypatch,tmp_path):
    ledger_file=tmp_path/'budget.json'
    monkeypatch.setattr(settings,'OPENAI_API_KEY','test-secret')
    monkeypatch.setattr(settings,'LUNA_BUDGET_LEDGER_FILE',str(ledger_file))
    monkeypatch.setattr(settings,'LUNA_BUDGET_KRW',20.0)
    class OverrunClient:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,**kwargs):
            if url.endswith('/input_tokens'):
                return luna_client.httpx.Response(200,json={'input_tokens':1000})
            body={'status':'completed','usage':{'input_tokens':50000,'output_tokens':6000},'output':[{'content':[{'type':'output_text','text':json.dumps({**sample(),'c':{'doc_type':'printed_receipt','support_status':'supported','issues':[],'affected_regions':[],'readable_summary':None,'reasoning':'인쇄된 구매 영수증'}})}]}]}
            return luna_client.httpx.Response(200,json=body,headers={'x-request-id':'req_overrun'})
    monkeypatch.setattr(luna_client.httpx,'AsyncClient',OverrunClient)
    res=asyncio.run(luna_client.recognize(b'image','image/png'))
    assert res['request_id']=='req_overrun'
    saved_ledger=json.loads(ledger_file.read_text(encoding='utf-8'))
    att=saved_ledger['attempts'][0]
    assert att['reservation_exceeded'] is True
    assert att['status']=='reservation_exceeded'
    assert att['cost_krw']>att['reserved_krw']

def test_deadline_releases_lock(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'OPENAI_API_KEY','test-secret')
    monkeypatch.setattr(settings,'LUNA_BUDGET_LEDGER_FILE',str(tmp_path/'budget.json'))
    monkeypatch.setattr(settings,'LUNA_TIMEOUT_SECONDS',.01)
    async def waiting(*a):await asyncio.sleep(1)
    monkeypatch.setattr(luna_client,'_recognize',waiting)
    with pytest.raises(luna_client.LunaFailure,match='TIMEOUT'):asyncio.run(luna_client.recognize(b'image','image/png'))
    assert not (tmp_path/'budget.lock').exists()

def test_partial_fields_persist_and_are_exposed(client,monkeypatch):
    from app.auth import service as auth
    from app.business.schemas import BusinessVerifyResponse
    from app.receipts import service
    from io import BytesIO
    from PIL import Image
    monkeypatch.setattr(auth,'verify_business',lambda _:BusinessVerifyResponse(business_number='1234567890',business_status='계속사업자',business_status_code='01',tax_type='부가가치세 일반과세자',tax_type_code='01',verified=True))
    reg=client.post('/auth/register',json={'email':'partial@example.com','password':'correct-password','name':'검증','business_name':'검증','business_number':'123-45-67890','terms_accepted':True,'privacy_accepted':True,'marketing_accepted':False})
    headers={'Authorization':'Bearer '+reg.json()['access_token']}
    raw=sample();raw['h']['datetime']=None;doc=normalize(raw)
    async def partial(*a):return ocr_client.OcrResult(vendor='검토상점',amount=11000,date=None,ocr_raw=json.dumps({'engine':'luna_low','document':doc,'confirmed':False}),review_required=True,engine='luna_low')
    monkeypatch.setattr(ocr_client,'extract_receipt',partial)
    b=BytesIO();Image.new('RGB',(4,4)).save(b,format='PNG')
    response=client.post('/receipts',headers=headers,files={'file':('receipt.png',b.getvalue(),'image/png')})
    assert response.status_code==201
    body=response.json();assert body['status']=='done' and body['vendor']=='검토상점' and body['date'] is None
    assert body['recognition']['document']['items'][0]['name']=='상품'
    assert client.get('/receipts/'+str(body['id']),headers=headers).json()==body

def test_worker_adapter_preserves_partial_and_reports_combined_stages(monkeypatch):
    from app.ocr_pipeline import luna
    from app.ocr_pipeline.contract import OcrPipelineInput
    raw=sample();raw['h']['datetime']=None
    async def fake(image,mime):return {'image_sha256':luna.hashlib.sha256(image).hexdigest(),'engine':'luna_low','document':normalize(raw),'confirmed':False}
    monkeypatch.setattr(luna,'recognize',fake);events=[]
    result=luna.LunaLowPipeline().process(OcrPipelineInput(receipt_id=1,image_bytes=b'image',content_type='image/png'),events.append)
    assert result.status=='PARTIAL' and result.vendor=='검토상점' and result.amount==11000
    assert 'transaction_date' in result.missing_fields
    assert events[0].status.value=='skipped'
    assert events[1].stage.value=='text_recognition' and events[1].status.value=='processing'
    assert any(e.stage.value=='transaction_extraction' and e.status.value=='completed' for e in events)
    assert json.loads(result.raw_text)['document']['items'][0]['quantity'] is None

def test_worker_failure_has_no_automatic_fallback(monkeypatch):
    from app.ocr_pipeline import luna
    from app.ocr_pipeline.contract import OcrPipelineInput
    async def fail(*a):raise luna_client.LunaFailure('BUDGET_EXCEEDED')
    monkeypatch.setattr(luna,'recognize',fail)
    result=luna.LunaLowPipeline().process(OcrPipelineInput(receipt_id=1,image_bytes=b'image',content_type='image/png'),lambda e:None)
    assert result.status=='FAILED' and result.pipeline_name=='luna_low'
    assert json.loads(result.raw_text)['error_code']=='BUDGET_EXCEEDED'
