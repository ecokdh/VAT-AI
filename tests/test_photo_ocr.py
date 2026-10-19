import asyncio
import copy
import hashlib
import json

import httpx
import pytest

from app.core.config import settings
from app.receipts import luna_client, photo_ocr
from app.receipts.subtotal_guard import DEFAULT_CONFIG, select_subtotal


def raw_prediction():
    return {
        'c': {'doc_type': 'printed_receipt', 'support_status': 'supported', 'issues': [],
              'affected_regions': [], 'readable_summary': '영수증', 'reasoning': '인쇄됨'},
        'h': {'vendor': '검토상점', 'branch': None, 'business_number': None,
              'datetime': '2026-10-12 12:30:00'},
        'm': [{'role': 'payment', 'scope': 'unknown', 'label': '카드 결제', 'value': 11000},
              {'role': 'subtotal', 'scope': 'unknown', 'label': '합계', 'value': 11000}],
        'i': [{'n': '상품', 'q': None, 'u': None, 'p': 11000, 't': 'item', 'parent': None}],
        'uncertain': [],
        'details': {k: None for k in ['address', 'phone', 'payment_method', 'approval_number',
                                      'receipt_number', 'approval_datetime', 'printed_datetime']},
    }


def ocr_response():
    return {'requestId': 'naver-request', 'images': [{'inferResult': 'SUCCESS', 'fields': [
        {'inferText': '합계', 'inferConfidence': .97, 'boundingPoly': {'vertices': [{'x': 1, 'y': 2}]},
         'lineBreak': False, 'type': 'NORMAL'},
        {'inferText': '11,000', 'inferConfidence': .96, 'lineBreak': True}]}]}


def test_hybrid_payload_and_originals_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'LUNA_INPUT_MODE', 'photo_ocr')
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', 'fixture')
    monkeypatch.setattr(settings, 'CLOVA_OCR_API_URL', 'https://naver.invalid/general')
    monkeypatch.setattr(settings, 'CLOVA_OCR_SECRET_KEY', 'fixture')
    monkeypatch.setattr(settings, 'LUNA_BUDGET_LEDGER_FILE', str(tmp_path / 'budget.json'))
    calls = []
    raw = raw_prediction()
    raw['details']['approval_number'] = '001234'
    original = copy.deepcopy(raw)

    class Transport:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if 'naver.invalid' in url:
                assert kwargs['json']['images'][0]['data'] == 'aW1hZ2U='
                return httpx.Response(200, json=ocr_response())
            if url.endswith('/input_tokens'):
                return httpx.Response(200, json={'input_tokens': 2000})
            payload = kwargs['json']
            content = payload['input'][1]['content']
            assert any(c['type'] == 'input_image' for c in content)
            assert '11,000' in content[-1]['text'] and 'boundingPoly' in content[-1]['text']
            assert payload['reasoning']['effort'] == 'low'
            return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 2000, 'output_tokens': 1000},
                'output': [{'content': [{'type': 'output_text', 'text': json.dumps(raw)}]}]})

    monkeypatch.setattr(luna_client.httpx, 'AsyncClient', Transport)
    result = asyncio.run(luna_client.recognize(b'image', 'image/png'))
    assert len(calls) == 3  # one OCR, count, one generation; no fallback/retry
    assert result['raw_prediction'] == original
    assert result['ocr']['raw_response'] == ocr_response()
    assert result['image_sha256'] == result['ocr']['image_sha256'] == hashlib.sha256(b'image').hexdigest()
    assert result['document']['fields']['subtotal_amount'] is None
    assert result['document']['fields']['payment_amount'] == 11000
    assert result['document']['fields']['approval_number'] == '001234'
    assert result['document']['printed_amounts'] == original['m']
    ledger = json.loads((tmp_path / 'budget.json').read_text())
    assert ledger['attempts'][0]['status'] == 'usage_recorded'


@pytest.mark.parametrize('status,body,code', [
    (401, {}, 'NAVER_HTTP_401'),
    (200, {'images': [{'inferResult': 'FAILURE'}]}, 'NAVER_INFERENCE_FAILED'),
    (200, {'images': [{'inferResult': 'SUCCESS', 'fields': 'bad'}]}, 'NAVER_INVALID_OUTPUT'),
])
def test_ocr_failure_never_calls_luna(monkeypatch, tmp_path, status, body, code):
    monkeypatch.setattr(settings, 'LUNA_INPUT_MODE', 'photo_ocr')
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', 'fixture')
    monkeypatch.setattr(settings, 'CLOVA_OCR_API_URL', 'https://naver.invalid/general')
    monkeypatch.setattr(settings, 'CLOVA_OCR_SECRET_KEY', 'fixture')
    monkeypatch.setattr(settings, 'LUNA_BUDGET_LEDGER_FILE', str(tmp_path / 'budget.json'))
    calls = []
    class Transport:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            calls.append(url)
            return httpx.Response(status, json=body)
    monkeypatch.setattr(luna_client.httpx, 'AsyncClient', Transport)
    with pytest.raises(luna_client.LunaFailure, match=code):
        asyncio.run(luna_client.recognize(b'image', 'image/png'))
    assert calls == ['https://naver.invalid/general']


@pytest.mark.parametrize('label,text,value,expected', [
    ('소계', '소계 1,000', 1000, 1000), ('소계', '소계 0', 0, 0),
    ('할인 전 금액', '할인 전 금액 1,000', 1000, 1000),
    ('합계', '합계 1,000', 1000, None), ('조제금액', '조제금액 1,000', 1000, None),
    ('소계', '합계 1,000', 1000, None), ('소계', '소계', None, None),
])
def test_subtotal_evidence(label, text, value, expected):
    assert select_subtotal([{'role': 'subtotal', 'label': label, 'value': value}], text, DEFAULT_CONFIG)['value'] == expected


def test_subtotal_conflict_and_total_equality():
    amounts = [{'role': 'subtotal', 'label': '소계', 'value': 1000}, {'role': 'total', 'label': '합계', 'value': 1000}]
    assert select_subtotal(amounts, '소계 1000 합계 1000', DEFAULT_CONFIG)['value'] == 1000
    amounts.append({'role': 'subtotal', 'label': '소계', 'value': 2000})
    assert select_subtotal(amounts, '소계 1000 소계 2000', DEFAULT_CONFIG)['value'] is None


@pytest.mark.parametrize('long_ocr', [False, True])
def test_hybrid_upload_worker_review_and_vault(client, monkeypatch, tmp_path, long_ocr):
    """Exercise the actual worker/client/normalizer; only HTTP providers are fixtures."""
    from tests.test_luna_edge_cases_e2e import _make_png_bytes, _register_user
    from app.main import app
    from app.core.database import get_session
    from app.jobs import worker
    headers = _register_user(client, monkeypatch, 'photo-ocr-e2e@example.com')
    monkeypatch.setattr(settings, 'LUNA_INPUT_MODE', 'photo_ocr')
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', 'fixture')
    monkeypatch.setattr(settings, 'CLOVA_OCR_API_URL', 'https://naver.invalid/general')
    monkeypatch.setattr(settings, 'CLOVA_OCR_SECRET_KEY', 'fixture')
    monkeypatch.setattr(settings, 'LUNA_BUDGET_LEDGER_FILE', str(tmp_path / 'budget.json'))
    prediction = raw_prediction()
    provider_ocr = ocr_response()
    if long_ocr:
        provider_ocr['images'][0]['fields'] *= 150
    prediction['details'].update(address='검증 주소', phone='02-001-0000', approval_number='001234')
    class Transport:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            if 'naver.invalid' in url: return httpx.Response(200, json=provider_ocr)
            if url.endswith('/input_tokens'): return httpx.Response(200, json={'input_tokens': 2000})
            return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 2000, 'output_tokens': 1000},
                'output': [{'content': [{'type': 'output_text', 'text': json.dumps(prediction)}]}]})
    monkeypatch.setattr(luna_client.httpx, 'AsyncClient', Transport)
    uploaded = client.post('/v2/receipt-jobs?direction=purchase', headers=headers,
        files={'file': ('receipt.png', _make_png_bytes(), 'image/png')})
    assert uploaded.status_code == 202, uploaded.text
    rid = uploaded.json()['receipt_id']
    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        monkeypatch.setattr(worker, 'engine', session.get_bind())
        assert worker.process_one()
    finally:
        gen.close()
    extracted = client.get(f'/v2/receipts/{rid}', headers=headers).json()
    assert extracted['status'] in {'done', 'needs_edit'}
    assert extracted['details']['address'] == '검증 주소'
    assert extracted['details']['phone'] == '02-001-0000'
    assert extracted['details']['approval_number'] == '001234'
    original = extracted['recognition']['raw_prediction']
    if long_ocr:
        assert len(extracted['ocr_raw']) > 40000
    doc = extracted['recognition']['document']
    assert doc['fields']['subtotal_amount'] is None
    from app.receipts.schemas import ReviewedFields
    doc = {'fields': {k: v for k, v in doc['fields'].items() if k in ReviewedFields.model_fields},
           'items': doc['items']}
    doc['items'][0].update(name='수정 상품', source_row=0, raw_name='위조 시도')
    confirmed = client.post(f'/v2/receipts/{rid}/confirm-extraction', headers=headers, json={
        'vendor': '검토상점', 'amount': 11000, 'date': '2026-10-12', 'document': doc,
        'details': extracted['details'], 'question_answers': {'use': 'business'}})
    assert confirmed.status_code == 200, confirmed.text
    loaded = client.get(f'/v2/receipts/{rid}', headers=headers).json()
    assert loaded['recognition']['raw_prediction'] == original
    assert loaded['review']['document']['items'][0]['raw_name'] == '상품'
    assert loaded['recognition']['ocr']['raw_response'] == provider_ocr
    saved = client.post(f'/v2/transactions/from-receipt/{rid}', headers=headers, json={
        'direction': 'purchase', 'transaction_date': '2026-10-12', 'vendor': '검토상점',
        'total_amount': 11000})
    assert saved.status_code == 201, saved.text
    vault = client.get('/v2/transactions?direction=purchase', headers=headers).json()
    assert any(t['receipt_id'] == rid and t['total_amount'] == 11000 for t in vault)
