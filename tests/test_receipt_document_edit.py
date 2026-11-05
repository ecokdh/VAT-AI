import json
from datetime import date

from app.auth.models import User
from app.core.database import get_session
from app.core.security import create_access_token
from app.main import app
from app.receipts.models import Receipt
from app.transactions.models import Transaction

DOC = {'fields': {'vendor': '서원위생상사', 'business_number': '619-01-10099', 'transaction_datetime': '2026-06-30 00:26:00', 'payment_amount': 13200, 'supply_amount': 12000, 'vat_amount': 1200},
       'items': [{'name': '주방세제 3L', 'raw_name': '주방세제 3L', 'source_row': 0, 'quantity': 2, 'unit_price': 6600, 'line_amount': 13200, 'row_type': 'item', 'parent_row': None}]}


def setup(client):
    gen = app.dependency_overrides[get_session](); s = next(gen)
    u = User(email='edit@example.com', name='테스트', password_hash='fixture'); s.add(u); s.flush()
    r = Receipt(user_id=u.id, image_url='fixture.png', status='done', direction='purchase', extraction_confirmed=True,
                vendor='서원위생상사', amount=13200, date=date(2026, 6, 30), ocr_raw=json.dumps({'engine': 'luna_low', 'document': DOC, 'review': {'document': DOC}}, ensure_ascii=False))
    s.add(r); s.flush()
    t = Transaction(user_id=u.id, receipt_id=r.id, direction='purchase', transaction_date=date(2026, 6, 30), vendor='서원위생상사', description='주방세제 3L',
                    total_amount=13200, supply_amount=12000, vat_amount=1200, state='confirmed', review_status='analyzed')
    s.add(t); s.commit(); s.refresh(t)
    return gen, s, r, t, {'Authorization': 'Bearer ' + create_access_token(u.id, u.email)}


def test_edit_updates_receipt_review_and_transaction(client):
    gen, s, r, t, h = setup(client)
    try:
        edited = json.loads(json.dumps(DOC))
        edited['fields'].update(business_number='619-01-99999', payment_amount=19800, supply_amount=18000, vat_amount=1800, transaction_datetime='2026-06-29')
        edited['items'][0].update(name='주방세제 5L', quantity=3, line_amount=19800)
        res = client.put(f'/v2/transactions/{t.id}/receipt-document', headers=h, json={'document': edited})
        assert res.status_code == 200, res.text
        body = res.json()
        assert (body['vendor'], body['transaction_date'], body['total_amount'], body['supply_amount'], body['vat_amount'], body['description']) == ('서원위생상사', '2026-06-29', 19800, 18000, 1800, '주방세제 5L')
        assert body['review_status'] == 'stale'  # 금액이 바뀌었으므로 다시 분석해야 한다
        s.expire_all(); saved = s.get(Receipt, r.id)
        review = json.loads(saved.ocr_raw)['review']
        assert review['document']['items'][0]['quantity'] == 3 and review['field_sources']['business_number'] == 'user_edit'
        assert saved.details['business_number'] == '619-01-99999' and saved.amount == 19800
    finally:
        gen.close()


def test_edit_rejects_negative_amount_and_saves_receipt_only_changes(client):
    gen, s, r, t, h = setup(client)
    try:
        bad = json.loads(json.dumps(DOC)); bad['fields']['payment_amount'] = -1
        assert client.put(f'/v2/transactions/{t.id}/receipt-document', headers=h, json={'document': bad}).status_code == 400
        same = json.loads(json.dumps(DOC)); same['fields']['business_number'] = '619-01-00000'
        res = client.put(f'/v2/transactions/{t.id}/receipt-document', headers=h, json={'document': same})
        assert res.status_code == 200 and res.json()['review_status'] == 'analyzed'  # 거래 값이 같으면 분석 결과 유지
        s.expire_all()
        assert s.get(Receipt, r.id).details['business_number'] == '619-01-00000'
    finally:
        gen.close()


def test_edit_saves_extra_receipt_details(client):
    gen, s, r, t, h = setup(client)
    try:
        res = client.put(f'/v2/transactions/{t.id}/receipt-document', headers=h, json={'document': DOC, 'details': {'address': '청주시 서원구', 'payment_method': '사업용 신한카드', 'additional_fields': [{'label': '메모', 'value': '매장용'}]}})
        assert res.status_code == 200, res.text
        s.expire_all(); d = s.get(Receipt, r.id).details
        assert (d['address'], d['payment_method'], d['additional_fields']) == ('청주시 서원구', '사업용 신한카드', [{'label': '메모', 'value': '매장용'}])
        assert d['business_number'] == '619-01-10099'
    finally:
        gen.close()
