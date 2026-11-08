"""Local-only Luna low recognition, bounded spend, no OCR fallback or retries."""
from __future__ import annotations
import asyncio,base64,hashlib,json,math,os,time,uuid
from pathlib import Path
from typing import Any
import httpx
from dotenv import dotenv_values
from app.core.config import settings
from app.receipts.luna_low_contract import MODEL,EFFORT,MAX_OUTPUT_TOKENS,SCHEMA,LEGACY_SCHEMA,CONTRACT_VERSION,normalize
from app.receipts.line_structure import STRUCTURE_VERSION, active_contract, structure_from_model, to_compact_raw
from app.receipts import photo_ocr

class LunaFailure(Exception):
    def __init__(self,code):self.code=code;self.ocr=None;super().__init__(code)

def validate(value:Any,schema:dict,path='root'):
    kinds=schema['type'];kinds=kinds if isinstance(kinds,list) else [kinds]
    matches={'null':value is None,'string':isinstance(value,str),'number':isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value),'integer':isinstance(value,int) and not isinstance(value,bool),'array':isinstance(value,list),'object':isinstance(value,dict)}
    if not any(matches.get(k,False) for k in kinds):raise LunaFailure('INVALID_OUTPUT_TYPE')
    if 'enum' in schema and value not in schema['enum']:raise LunaFailure('INVALID_OUTPUT_ENUM')
    if isinstance(value,dict):
        if set(value)!=set(schema['properties']):raise LunaFailure('INVALID_OUTPUT_KEYS')
        for k,v in value.items():validate(v,schema['properties'][k],path+'.'+k)
    elif isinstance(value,list):
        for v in value:validate(v,schema['items'],path+'[]')

def checked_normalize(raw):
    if 'c' in raw:
        validate(raw, SCHEMA)
    else:
        validate(raw, LEGACY_SCHEMA)
    for i,item in enumerate(raw['i']):
        parent=item['parent']
        if parent is not None and (parent<0 or parent>=len(raw['i']) or parent==i or raw['i'][parent]['t']!='item'):raise LunaFailure('INVALID_ITEM_PARENT')
    return normalize(raw)

def atomic(path,obj):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def usage_cost(u):
    d=u.get('input_tokens_details') or {};c=d.get('cached_tokens',0);w=d.get('cache_write_tokens',0)
    return (max(0,u.get('input_tokens',0)-c-w)*.1+c*.01+w*.125+u.get('output_tokens',0)*.5)/1e6*2200

async def recognize(image_bytes:bytes,mime_type:str):
    key=settings.OPENAI_API_KEY
    if not key and settings.LUNA_API_KEY_FILE:key=dotenv_values(settings.LUNA_API_KEY_FILE).get('OPENAI_API_KEY','')
    if not key:raise LunaFailure('API_KEY_MISSING')
    if mime_type not in {'image/jpeg','image/png'}:raise LunaFailure('UNSUPPORTED_IMAGE')
    if settings.LUNA_INPUT_MODE not in {'photo', 'photo_ocr'}:raise LunaFailure('INVALID_INPUT_MODE')
    ledger_path=Path(settings.LUNA_BUDGET_LEDGER_FILE);ledger_path.parent.mkdir(parents=True,exist_ok=True)
    lock_path=ledger_path.with_suffix('.lock')
    if lock_path.exists():
        try:
            if time.time() - lock_path.stat().st_mtime > settings.LUNA_TIMEOUT_SECONDS + 5.0:
                lock_path.unlink(missing_ok=True)
        except OSError:
            pass
    try:fd=os.open(lock_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise LunaFailure('RECOGNITION_BUSY')
    os.close(fd)
    context={}
    try:
        return await asyncio.wait_for(_recognize(image_bytes,mime_type,key,ledger_path,context),timeout=settings.LUNA_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        exc=LunaFailure('TIMEOUT');exc.ocr=context.get('ocr');raise exc from None
    except httpx.RequestError:
        exc=LunaFailure('NETWORK_ERROR');exc.ocr=context.get('ocr');raise exc from None
    except LunaFailure as exc:
        exc.ocr=context.get('ocr')
        raise
    finally:lock_path.unlink(missing_ok=True)

async def _recognize(image_bytes,mime_type,key,ledger_path,context=None):
    ledger=json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {'cap_krw':settings.LUNA_BUDGET_KRW,'attempts':[]}
    prompt,schema,version=active_contract()
    ocr=None
    if settings.LUNA_INPUT_MODE == 'photo_ocr':
        # Do not spend on OCR when even the minimum model reservation cannot fit.
        exposure=sum(a.get('cost_krw',a.get('reserved_krw',0)) for a in ledger['attempts'])
        minimum_reserve=(1024*.125+MAX_OUTPUT_TOKENS*.5)/1e6*2200
        if exposure+minimum_reserve>min(settings.LUNA_BUDGET_KRW,ledger.get('cap_krw',settings.LUNA_BUDGET_KRW)):
            raise LunaFailure('BUDGET_EXCEEDED')
        ocr_attempt={'image_sha256':hashlib.sha256(image_bytes).hexdigest(),'status':'requested_usage_unverified','time':time.time(),'cost_krw':None}
        ledger.setdefault('ocr_attempts',[]).append(ocr_attempt);atomic(ledger_path,ledger)
        try:ocr=await photo_ocr.recognize_general(image_bytes,mime_type)
        except photo_ocr.GeneralOcrFailure as exc:raise LunaFailure(str(exc)) from None
        if context is not None:context['ocr']=ocr
        ocr_attempt.update(status='response_recorded',request_id=ocr['request_id'],seconds=ocr['seconds'])
        atomic(ledger_path,ledger)
        if ocr['image_sha256'] != hashlib.sha256(image_bytes).hexdigest():raise LunaFailure('OCR_IMAGE_MISMATCH')
        prompt,schema,version=photo_ocr.contract()
    payload={'model':MODEL,'store':False,'reasoning':{'effort':EFFORT},'max_output_tokens':MAX_OUTPUT_TOKENS,'input':[{'role':'system','content':prompt},{'role':'user','content':[{'type':'input_text','text':'원본 영수증 전체를 추출하세요.'},{'type':'input_image','image_url':'data:'+mime_type+';base64,'+base64.b64encode(image_bytes).decode(),'detail':'high'}]}],'text':{'format':{'type':'json_schema','name':'receipt','strict':True,'schema':schema}}}
    if ocr is not None:
        payload['input'][1]['content'].append({'type':'input_text','text':'[네이버 CLOVA General OCR 전체 토큰 자료]\n'+json.dumps(ocr['input'],ensure_ascii=False,separators=(',',':'))})
    headers={'Authorization':'Bearer '+key}
    async with httpx.AsyncClient(timeout=settings.LUNA_TIMEOUT_SECONDS) as client:
        count=await client.post('https://api.openai.com/v1/responses/input_tokens',headers=headers,json={k:payload[k] for k in ['model','input','text']})
        if count.status_code!=200:raise LunaFailure('TOKEN_COUNT_HTTP_'+str(count.status_code))
        tokens=int(count.json()['input_tokens']);reserve=((tokens*1.2+1024)*.125+MAX_OUTPUT_TOKENS*.5)/1e6*2200
        exposure=sum(a.get('cost_krw',a['reserved_krw']) for a in ledger['attempts'])
        if exposure+reserve>min(settings.LUNA_BUDGET_KRW,ledger.get('cap_krw',settings.LUNA_BUDGET_KRW)):raise LunaFailure('BUDGET_EXCEEDED')
        attempt={'attempt_id':str(uuid.uuid4()),'reserved_krw':reserve,'status':'reserved','source':'local_mvp_luna_low','image_sha256':hashlib.sha256(image_bytes).hexdigest(),'time':time.time(),'counted_input_tokens':tokens}
        ledger['attempts'].append(attempt);atomic(ledger_path,ledger);start=time.monotonic()
        try:
            response=await client.post('https://api.openai.com/v1/responses',headers=headers,json=payload)
            attempt['request_id']=response.headers.get('x-request-id');attempt['http_status']=response.status_code
            if response.status_code!=200:raise LunaFailure('MODEL_HTTP_'+str(response.status_code))
            raw=response.json();usage=raw.get('usage') or {}
            if usage:
                cost=usage_cost(usage)
                attempt.update(cost_krw=cost,usage=usage,status='reservation_exceeded' if cost>reserve else 'usage_recorded',reservation_exceeded=cost>reserve)
            if raw.get('status')!='completed':raise LunaFailure('INCOMPLETE_OUTPUT')
            text=''.join(c.get('text','') for o in raw.get('output',[]) for c in o.get('content',[]) if c.get('type')=='output_text')
            parsed=json.loads(text)
            validate(parsed,schema)
            if ocr is not None:
                document=photo_ocr.normalize_prediction(parsed,ocr,checked_normalize)
            elif version==STRUCTURE_VERSION:
                structured=structure_from_model(parsed)
                document=checked_normalize(to_compact_raw(structured))
                document['line_structure']=structured
            else:
                document=checked_normalize(parsed)
            contract_sha=hashlib.sha256(json.dumps({'prompt':prompt,'schema':schema,'version':version},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            return {'engine':'luna_low','input_mode':settings.LUNA_INPUT_MODE,'ocr':ocr,'model_response':raw,'model':MODEL,'reasoning_effort':EFFORT,'contract_version':version,'contract_sha256':contract_sha,'image_sha256':attempt['image_sha256'],'request_id':attempt['request_id'],'document':document,'raw_prediction':parsed,'usage':usage,'seconds':time.monotonic()-start,'confirmed':False}
        except (ValueError,KeyError,TypeError):raise LunaFailure('INVALID_OUTPUT') from None
        finally:
            attempt['seconds']=time.monotonic()-start;atomic(ledger_path,ledger)
