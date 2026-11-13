import json
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from PIL import Image

from app.auth.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.sales_monthly import service, tax_lines
from app.sales_monthly.models import MonthlySalesDocument
from app.transactions import service as transactions
from tests.test_vat_return import finalize_sales, setup_session


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


def test_sales_photo_recognition_is_removed(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.post('/sales/monthly/extract',files={'file':('x.png', png(), 'image/png')}).status_code in (404, 405)


def seed_document(user_id):
    session = next(app.dependency_overrides[get_session]())
    item = MonthlySalesDocument(user_id=user_id, image_key='k', image_mime='image/png', image_sha256='h', raw_prediction_json='{}',
        review_json=json.dumps(example(), ensure_ascii=False), ocr_json='{}', model_response_json='{}', contract_version=service.CONTRACT_VERSION)
    session.add(item); session.commit(); session.refresh(item)
    return item.id


def row(name, payment, tax, total, supply=None):
    return {'원문항목':name,'결제수단':payment,'과세구분':tax,'합계금액':total,'공급가액':supply,'부가세':None}


def test_row_lines_map_payment_and_estimate_supply():
    document = {**example(), '매출집계_유형별':[row('신용카드','카드','과세',11000), row('현금영수증','현금','과세',5500,5000),
        row('계좌이체','계좌이체',None,3000), row('면세품','현금','면세',2000), row('상품권','기타','과세',0), row('포인트','포인트','과세',None)]}
    lines = tax_lines.row_lines(document)
    assert [(l['evidence_type'], l['tax_treatment'], l['supply_amount'], l['vat_amount'], l['supply_estimated']) for l in lines] == [
        ('card_receipt','standard',10000,1000,True), ('cash_receipt','standard',5000,500,False),
        ('other','unknown',None,None,False), ('other','exempt',2000,0,False)]


def test_pos_settlement_is_never_reportable_sales():
    """POS 월정산은 검토·휴지통 여부와 관계없이 신고 매출에 들어가지 않는다."""
    session, user = setup_session()
    document = {**example(), '거래일':'2026-03', '매출집계_유형별':[row('신용카드','카드','과세',1_100_000)]}
    item = MonthlySalesDocument(user_id=user.id, image_key='k', image_mime='image/png', image_sha256='h', raw_prediction_json='{}',
        review_json=json.dumps(document, ensure_ascii=False), ocr_json='{}', model_response_json='{}', contract_version=service.CONTRACT_VERSION, status='reviewed')
    session.add(item); session.commit()
    assert transactions.calculate_period_estimate(session, user, '2026-H1', None)['output_vat'] is None  # 매출 집계 확정 전
    finalize_sales(session, user)
    assert transactions.calculate_period_estimate(session, user, '2026-H1', None)['output_vat'] == 0
    item.deleted_at = datetime.now(timezone.utc); session.add(item); session.commit()
    assert transactions.calculate_period_estimate(session, user, '2026-H1', None)['output_vat'] == 0


def test_lines_preview_excludes_pos_settlement_without_saving(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    document = {**example(), '매출집계_유형별':[row('신용카드','카드','과세',11000), row('계좌이체','계좌이체',None,3000)]}
    body = client.post('/sales/monthly/lines', json={'document':document}).json()
    assert (body['output_vat'], body['excluded_count'], body['month_valid'], body['reportable']) == (None, 2, True, False)
    assert client.get('/sales/monthly').json() == []


def test_trash_hides_document_from_list_and_tax_and_restore_brings_it_back(client):
    user_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    doc_id = seed_document(user_id)
    assert client.delete(f'/sales/monthly/{doc_id}').status_code == 409  # 휴지통에 없으면 영구 삭제하지 않는다
    assert client.post(f'/sales/monthly/{doc_id}/trash').json()['deleted_at'] is not None
    assert client.get('/sales/monthly').json() == [] and client.get('/sales/monthly/trash').json()[0]['id'] == doc_id
    assert client.post(f'/sales/monthly/{doc_id}/restore').json()['deleted_at'] is None
    assert client.get('/sales/monthly').json()[0]['id'] == doc_id and client.get('/sales/monthly/trash').json() == []
    client.post(f'/sales/monthly/{doc_id}/trash')
    assert client.delete(f'/sales/monthly/{doc_id}').status_code == 204
    assert client.get('/sales/monthly/trash').json() == [] and client.get(f'/sales/monthly/{doc_id}').status_code == 404
