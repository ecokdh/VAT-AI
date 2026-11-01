from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.main import app
from app.receipts.luna_client import LunaFailure
from app.sales_monthly import service


def example():
    return {'사업장':{'상호':'가게','사업자등록번호':None},'거래일':'2026-10',
        '집계합계':{'총판매액':100,'총할인액':-10,'취소환불액':-5,'실매출액':80,'과세공급가액':None,'부가세합계':None,'면세매출액':None},
        '매출집계_유형별':[{'원문항목':'카드','결제수단':'카드','과세구분':None,'합계금액':80,'공급가액':None,'부가세':None}],
        '세무조정_필수항목':{'할인액':-10,'취소환불액':-5,'포인트사용액':None,'현금영수증발행액':None}}


def png():
    buf = BytesIO(); Image.new('RGB',(8,8),'white').save(buf,format='PNG'); return buf.getvalue()


def test_normalization_keeps_raw_and_flags_mismatch():
    source = example(); result = service.prepare_review(source)
    assert source['집계합계']['총할인액'] == -10
    assert result['raw_prediction']['집계합계']['총할인액'] == -10
    assert result['document']['집계합계']['총할인액'] == 10
    assert result['document']['집계합계']['실매출액'] == 80
    assert result['document']['집계합계']['면세매출액'] is None
    assert len(result['warnings']) == 1


def test_validate_image_rejects_mismatched_content_and_dimensions(monkeypatch):
    service.validate_image(png(), 'image/png')
    with pytest.raises(LunaFailure): service.validate_image(png(), 'image/jpeg')
    monkeypatch.setattr(settings, 'MAX_IMAGE_PIXELS', 10)
    with pytest.raises(LunaFailure): service.validate_image(png(), 'image/png')


def test_endpoint_requires_authentication(client):
    response = client.post('/sales/monthly/extract',files={'file':('x.png', png(), 'image/png')})
    assert response.status_code == 401


def test_endpoint_returns_structured_review_without_changing_transaction_store(client, monkeypatch):
    user_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    fake = AsyncMock(return_value={**service.prepare_review(example()), 'ocr_response':{'source':'test'}, 'model_response':{'source':'test'}, 'contract_version':service.CONTRACT_VERSION})
    monkeypatch.setattr(service, 'recognize', fake)
    response = client.post('/sales/monthly/extract',files={'file':('x.png', png(), 'image/png')})
    assert response.status_code == 201
    assert response.json()['raw_prediction']['집계합계']['총할인액'] == -10
    assert response.json()['document']['집계합계']['총할인액'] == 10
    fake.assert_awaited_once()
    doc_id = response.json()['id']
    assert client.get('/sales/monthly').json()[0]['id'] == doc_id
    assert client.get(f'/sales/monthly/{doc_id}/image').content == png()
    edited = response.json()['document']; edited['사업장']['상호'] = '수정한 상호'
    review = client.put(f'/sales/monthly/{doc_id}/review',json={'document':edited})
    assert review.status_code == 200 and review.json()['status'] == 'reviewed'
    assert client.get(f'/sales/monthly/{doc_id}').json()['document']['사업장']['상호'] == '수정한 상호'
    assert client.get(f'/sales/monthly/{doc_id}').json()['raw_prediction']['사업장']['상호'] == '가게'
    assert client.post('/sales/monthly/extract',files={'file':('x.png', png(), 'image/png')}).status_code == 409
    fake.assert_awaited_once()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.get('/sales/monthly').json() == []
    assert client.get(f'/sales/monthly/{doc_id}').status_code == 404
    assert client.get(f'/sales/monthly/{doc_id}/image').status_code == 404
    assert client.put(f'/sales/monthly/{doc_id}/review',json={'document':edited}).status_code == 404


def test_endpoint_rejects_invalid_image(client, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    async def fake(data, mime): service.validate_image(data, mime)
    assert client.post('/sales/monthly/extract',files={'file':('x.png', b'bad', 'image/png')}).status_code == 400
