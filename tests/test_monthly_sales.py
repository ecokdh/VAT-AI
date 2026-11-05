import json
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.main import app
from app.receipts.ocr.luna_client import LunaFailure
from app.sales_monthly import service, tax_lines
from app.sales_monthly.models import MonthlySalesDocument
from app.transactions import service as transactions
from app.vat_return.returns import build_vat_return
from tests.test_vat_return import setup_session


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
    again = client.post('/sales/monthly/extract',files={'file':('x.png', png(), 'image/png')})
    assert again.status_code == 201 and again.json()['id'] == doc_id  # 같은 사진은 다시 인식하지 않고 기존 정산서를 연다
    fake.assert_awaited_once()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.get('/sales/monthly').json() == []
    assert client.get(f'/sales/monthly/{doc_id}').status_code == 404
    assert client.get(f'/sales/monthly/{doc_id}/image').status_code == 404
    assert client.put(f'/sales/monthly/{doc_id}/review',json={'document':edited}).status_code == 404


def row(name, payment, tax, total, supply=None):
    return {'원문항목':name,'결제수단':payment,'과세구분':tax,'합계금액':total,'공급가액':supply,'부가세':None}


def test_row_lines_map_payment_and_estimate_supply():
    document = {**example(), '매출집계_유형별':[row('신용카드','카드','과세',11000), row('현금영수증','현금','과세',5500,5000),
        row('계좌이체','계좌이체',None,3000), row('면세품','현금','면세',2000), row('상품권','기타','과세',0), row('포인트','포인트','과세',None)]}
    lines = tax_lines.row_lines(document)
    assert [(l['evidence_type'], l['tax_treatment'], l['supply_amount'], l['vat_amount'], l['supply_estimated']) for l in lines] == [
        ('card_receipt','standard',10000,1000,True), ('cash_receipt','standard',5000,500,False),
        ('other','unknown',None,None,False), ('other','exempt',2000,0,False)]


def test_reviewed_document_is_included_in_estimate_and_return():
    session, user = setup_session()
    def save(month, status, rows):
        document = {**example(), '거래일':month, '매출집계_유형별':rows}
        session.add(MonthlySalesDocument(user_id=user.id, image_key=month+status, image_mime='image/png', image_sha256=month+status,
            raw_prediction_json='{}', review_json=json.dumps(document, ensure_ascii=False), ocr_json='{}', model_response_json='{}',
            contract_version=service.CONTRACT_VERSION, status=status))
    save('2026-03', 'reviewed', [row('신용카드','카드','과세',1_100_000), row('현금영수증','현금','과세',550_000), row('계좌이체','계좌이체','과세',330_000)])
    save('2026-04', 'needs_review', [row('신용카드','카드','과세',1_100_000)])
    save('2026-08', 'reviewed', [row('신용카드','카드','과세',1_100_000)])
    session.commit()
    estimate = transactions.calculate_period_estimate(session, user, '2026-H1', None)
    assert estimate['output_vat'] == 180_000
    result = build_vat_return(session, user, '2026-H1')
    assert (result['values']['r3.amount'], result['values']['r3.tax']) == ('1,500,000', '150,000')
    assert (result['values']['r4.amount'], result['values']['r4.tax']) == ('300,000', '30,000')
    assert not any('예상세액 계산과 다릅니다' in note for note in result['notes'])


def test_lines_preview_reports_output_vat_without_saving(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    document = {**example(), '매출집계_유형별':[row('신용카드','카드','과세',11000), row('계좌이체','계좌이체',None,3000)]}
    body = client.post('/sales/monthly/lines', json={'document':document}).json()
    assert (body['output_vat'], body['excluded_count'], body['month_valid']) == (1000, 1, True)
    assert client.get('/sales/monthly').json() == []


def test_trash_hides_document_from_list_and_tax_and_restore_brings_it_back(client, monkeypatch):
    user_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    fake = AsyncMock(return_value={**service.prepare_review(example()), 'ocr_response':{}, 'model_response':{}, 'contract_version':service.CONTRACT_VERSION})
    monkeypatch.setattr(service, 'recognize', fake)
    doc_id = client.post('/sales/monthly/extract',files={'file':('x.png', png(), 'image/png')}).json()['id']
    assert client.delete(f'/sales/monthly/{doc_id}').status_code == 409  # 휴지통에 없으면 영구 삭제하지 않는다
    assert client.post(f'/sales/monthly/{doc_id}/trash').json()['deleted_at'] is not None
    assert client.get('/sales/monthly').json() == [] and client.get('/sales/monthly/trash').json()[0]['id'] == doc_id
    # 휴지통에 있는 사진을 다시 올리면 새로 인식하지 않고 복원해서 연다.
    again = client.post('/sales/monthly/extract',files={'file':('x.png', png(), 'image/png')}).json()
    assert again['id'] == doc_id and again['deleted_at'] is None
    fake.assert_awaited_once()
    client.post(f'/sales/monthly/{doc_id}/trash')
    assert client.post(f'/sales/monthly/{doc_id}/restore').json()['deleted_at'] is None
    assert client.get('/sales/monthly').json()[0]['id'] == doc_id and client.get('/sales/monthly/trash').json() == []
    client.post(f'/sales/monthly/{doc_id}/trash')
    assert client.delete(f'/sales/monthly/{doc_id}').status_code == 204
    assert client.get('/sales/monthly/trash').json() == [] and client.get(f'/sales/monthly/{doc_id}').status_code == 404
    # 영구 삭제한 사진은 다시 올리면 새로 인식한다.
    client.post('/sales/monthly/extract',files={'file':('x.png', png(), 'image/png')})
    assert fake.await_count == 2


def test_trashed_document_is_left_out_of_estimate():
    session, user = setup_session()
    document = {**example(), '거래일':'2026-03', '매출집계_유형별':[row('신용카드','카드','과세',1_100_000)]}
    item = MonthlySalesDocument(user_id=user.id, image_key='k', image_mime='image/png', image_sha256='h', raw_prediction_json='{}',
        review_json=json.dumps(document, ensure_ascii=False), ocr_json='{}', model_response_json='{}', contract_version=service.CONTRACT_VERSION, status='reviewed')
    session.add(item); session.commit()
    assert transactions.calculate_period_estimate(session, user, '2026-H1', None)['output_vat'] == 100_000
    item.deleted_at = datetime.now(timezone.utc); session.add(item); session.commit()
    assert transactions.calculate_period_estimate(session, user, '2026-H1', None)['output_vat'] == 0


def test_endpoint_rejects_invalid_image(client, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    async def fake(data, mime): service.validate_image(data, mime)
    assert client.post('/sales/monthly/extract',files={'file':('x.png', b'bad', 'image/png')}).status_code == 400
