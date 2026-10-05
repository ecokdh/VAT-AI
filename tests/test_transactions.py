from datetime import date

import pytest

from app.receipts import ocr_client
from test_receipts import auth_headers, PNG_BYTES


@pytest.fixture
def setup_transactions(client, monkeypatch):
    async def fake_extract(*args):
        return ocr_client.OcrResult(vendor="거래 상점", amount=11000, date=date(2026, 10, 5),
            ocr_raw="거래 상점", business_number="1234567890", transaction_amount=11000,
            taxable_supply_amount=10000, tax_exempt_amount=0, vat_amount=1000,
            line_items=({"name": "상품", "quantity": 2, "printed_unit_price": 5000,
                         "line_amount": 10000, "sources": {"name": {"kind": "ocr", "state": "READ"}}},))
    monkeypatch.setattr(ocr_client, "extract_receipt", fake_extract)
    headers = auth_headers(client)
    def upload():
        response = client.post("/receipts", headers=headers, files={"file": ("receipt.png", PNG_BYTES, "image/png")})
        assert response.status_code == 201
        return response.json()
    def confirm(receipt):
        response = client.post(f"/receipts/{receipt['id']}/ocr/confirm", headers=headers,
            json={"confirmed": True, "base_revision": receipt["revision"]})
        assert response.status_code == 200, response.text
        return response.json()
    return headers, upload, confirm


def test_confirm_creates_separate_transaction_and_protected_handoff(client, setup_transactions):
    headers, upload, confirm = setup_transactions
    receipt = confirm(upload())
    transaction_id = receipt["transaction_id"]
    transaction = client.get(f"/transactions/{transaction_id}", headers=headers).json()
    assert transaction["facts"]["ocr_confirmed"] is True
    assert transaction["tax_analysis_confirmed"] is False
    assert transaction["integration_status"] == "LOCAL_CONTRACT_ONLY"
    assert transaction["facts"]["total_amount"] == 11000
    outsider = auth_headers(client, "transaction-outsider@example.com")
    assert client.get(f"/transactions/{transaction_id}", headers=outsider).status_code == 404
    assert client.get("/transactions", headers=outsider).json() == []
    assert client.get("/reconciliation/issues", headers=outsider).json() == []


def test_item_usage_edits_require_transaction_revision(client, setup_transactions):
    headers, upload, confirm = setup_transactions
    receipt = confirm(upload())
    transaction_id = receipt["transaction_id"]
    item_id = receipt["line_items"][0]["id"]
    path = f"/transactions/{transaction_id}/line-items/{item_id}"
    saved = client.patch(path, headers=headers, json={"base_revision": 1, "usage": "BUSINESS", "user_note": "업무용"})
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert client.patch(path, headers=headers, json={"base_revision": 1, "usage": "PERSONAL"}).status_code == 409
    items = client.get(f"/transactions/{transaction_id}/line-items", headers=headers).json()
    assert items[0]["id"] == item_id and items[0]["usage"] == "BUSINESS"


def test_same_file_is_only_candidate_until_explicit_merge(client, setup_transactions):
    headers, upload, confirm = setup_transactions
    a, b = confirm(upload()), confirm(upload())
    issues = client.get("/reconciliation/issues", headers=headers).json()
    assert len(issues) == 1 and issues[0]["reason"] == "SAME_FILE"
    assert issues[0]["resolved"] is False
    assert a["transaction_id"] != b["transaction_id"]
    path = f"/reconciliation/issues/{issues[0]['id']}/resolve"
    payload = {"action": "MERGE", "canonical_transaction_id": a["transaction_id"],
        "transaction_revisions": {a["transaction_id"]: 1, b["transaction_id"]: 1},
        "receipt_revisions": {str(b["id"]): b["revision"] - 1}}
    assert client.post(path, headers=headers, json=payload).status_code == 409
    assert client.get("/reconciliation/issues", headers=headers).json()[0]["resolved"] is False
    payload["receipt_revisions"][str(b["id"])] = b["revision"]
    assert client.post(path, headers=headers, json=payload).status_code == 200
    result = client.get(f"/transactions/{a['transaction_id']}", headers=headers).json()
    assert len(result["receipts"]) == 2
    assert len(result["canonical_line_items"]) == 1  # Supporting evidence is not another purchase.
    assert {r["id"] for r in result["receipts"]} == {a["id"], b["id"]}
    summaries = {r["id"]: r for r in client.get("/receipts", headers=headers).json()}
    assert summaries[b["id"]]["transaction_id"] == a["transaction_id"]
    assert summaries[b["id"]]["revision"] == b["revision"] + 1
    assert client.get(f"/transactions/{b['transaction_id']}", headers=headers).json()["workflow_status"] == "MERGED"
    assert client.post(path, headers=headers, json={"action": "SEPARATE"}).status_code == 409


def test_separate_keeps_both_receipts_and_transactions(client, setup_transactions):
    headers, upload, confirm = setup_transactions
    a, b = confirm(upload()), confirm(upload())
    issue = client.get("/reconciliation/issues", headers=headers).json()[0]
    assert client.post(f"/reconciliation/issues/{issue['id']}/resolve", headers=headers, json={"action": "SEPARATE"}).status_code == 200
    assert client.get(f"/receipts/{a['id']}", headers=headers).json()["transaction_id"] == a["transaction_id"]
    assert client.get(f"/receipts/{b['id']}", headers=headers).json()["transaction_id"] == b["transaction_id"]


def test_returns_keep_sign_original_link_and_reject_excess_refund(client, setup_transactions):
    headers, upload, confirm = setup_transactions
    receipt = confirm(upload())
    path = f"/transactions/{receipt['transaction_id']}/adjustments"
    payload = {"base_revision": 1, "adjustment_type": "RETURN", "supply_date": "2026-10-05",
        "supply_amount": -1000, "vat_amount": -100, "total_amount": -1100}
    adjustment = client.post(path, headers=headers, json=payload)
    assert adjustment.status_code == 201
    assert adjustment.json()["original_transaction_id"] == receipt["transaction_id"]
    assert adjustment.json()["facts"]["total_amount"] == -1100
    assert adjustment.json()["tax_analysis_confirmed"] is False
    assert client.post(path, headers=headers, json=payload).status_code == 409
    excessive = {**payload, "base_revision": 2, "supply_amount": -10000, "vat_amount": -1000, "total_amount": -11000}
    assert client.post(path, headers=headers, json=excessive).status_code == 409
    assert client.get(f"/transactions/{receipt['transaction_id']}", headers=headers).json()["revision"] == 2
    assert client.post(path, headers=headers, json={**payload, "base_revision": 2, "total_amount": 1100}).status_code == 400


def test_return_without_original_remains_unresolved(client, setup_transactions):
    headers, upload, confirm = setup_transactions
    receipt = upload()
    saved = client.patch(f"/receipts/{receipt['id']}/ocr", headers=headers, json={"base_revision": receipt["revision"],
        "document": {"adjustment_type": "RETURN"}, "amount": -11000, "taxable_supply_amount": -10000,
        "vat_amount": -1000, "tax_exempt_amount": 0, "transaction_amount": -11000}).json()
    receipt = confirm(saved)
    result = client.get(f"/transactions/{receipt['transaction_id']}", headers=headers).json()
    assert result["workflow_status"] == "UNRESOLVED_ADJUSTMENT"
    assert result["original_transaction_id"] is None
    assert result["facts"]["total_amount"] == -11000

    original = confirm(upload())
    path = f"/transactions/{receipt['transaction_id']}"
    payload = {"base_revision": result["revision"], "original_transaction_id": original["transaction_id"], "original_revision": 1}
    assert client.patch(path, headers=headers, json={**payload, "base_revision": result["revision"] + 1}).status_code == 409
    assert client.get(f"/transactions/{original['transaction_id']}", headers=headers).json()["revision"] == 1
    linked = client.patch(path, headers=headers, json=payload)
    assert linked.status_code == 200
    assert linked.json()["original_transaction_id"] == original["transaction_id"]
    assert linked.json()["workflow_status"] == "NEEDS_CONTEXT"
    assert linked.json()["facts"] == result["facts"]
    assert linked.json()["receipts"][0]["id"] == receipt["id"]
    assert client.patch(path, headers=headers, json=payload).status_code == 409
    # The linked receipt exhausts this sale; another refund cannot exceed it.
    assert client.post(f"/transactions/{original['transaction_id']}/adjustments", headers=headers,
        json={"base_revision": 2, "adjustment_type": "RETURN", "supply_date": "2026-10-05", "total_amount": -1}).status_code == 409


def test_phash_only_signals_similarity_and_never_merges():
    from app.receipts.models import Receipt
    from app.receipts.transactions import duplicate_reason
    a = Receipt(perceptual_hash="0000000000000001")
    b = Receipt(perceptual_hash="0000000000000003")
    assert duplicate_reason(a, b) == "SIMILAR_IMAGE"
    b.perceptual_hash = "ffffffffffffffff"
    assert duplicate_reason(a, b) is None


def test_corrected_signature_refreshes_activity_without_losing_user_decision(client, setup_transactions, monkeypatch):
    from app.receipts import service
    headers, upload, _ = setup_transactions
    hashes = iter((("image-a", "0000000000000000"), ("image-b", "ffffffffffffffff")))
    monkeypatch.setattr(service, "image_fingerprints", lambda _: next(hashes))
    a, b = upload(), upload()
    assert client.get("/reconciliation/issues", headers=headers).json() == []
    signature = {"approval_number": "12345678", "transaction_datetime": "2026-10-05T10:30:00"}

    def save(receipt, document):
        response = client.patch(f"/receipts/{receipt['id']}/ocr", headers=headers,
            json={"base_revision": receipt["revision"], "document": document})
        assert response.status_code == 200, response.text
        return response.json()

    a = save(a, signature)
    b = save(b, signature)
    issue = client.get("/reconciliation/issues", headers=headers).json()[0]
    assert issue["reason"] == "SAME_APPROVAL_SIGNATURE" and issue["active"] and not issue["resolved"]
    assert a["transaction_id"] is None and b["transaction_id"] is None
    assert client.get("/reconciliation/issues", headers=auth_headers(client, "another-owner@example.com")).json() == []
    b = save(b, {**signature, "approval_number": "87654321"})
    inactive = client.get("/reconciliation/issues", headers=headers).json()[0]
    assert inactive["id"] == issue["id"] and not inactive["active"] and not inactive["resolved"]
    assert inactive["action"] is None
    path = f"/reconciliation/issues/{issue['id']}/resolve"
    assert client.post(path, headers=headers, json={"action": "SEPARATE"}).status_code == 409
    b = save(b, signature)
    revived = client.get("/reconciliation/issues", headers=headers).json()
    assert len(revived) == 1 and revived[0]["id"] == issue["id"] and revived[0]["active"]
    assert client.post(path, headers=headers, json={"action": "SEPARATE"}).status_code == 200
    b = save(b, {**signature, "approval_number": "87654321"})
    b = save(b, signature)
    decided = client.get("/reconciliation/issues", headers=headers).json()
    assert len(decided) == 1 and decided[0]["resolved"] and decided[0]["active"] and decided[0]["action"] == "SEPARATE"
    assert decided[0]["id"] == issue["id"]
    assert client.get(f"/receipts/{b['id']}", headers=headers).json()["revision"] == b["revision"]


def test_duplicate_refresh_failure_rolls_back_receipt_save(client, setup_transactions, monkeypatch):
    from app.receipts import transactions
    from app.common.exceptions import AppException
    headers, upload, _ = setup_transactions
    a = upload()
    before = client.get(f"/receipts/{a['id']}", headers=headers).json()

    def fail_refresh(*args):
        raise AppException(400, "VALIDATION_ERROR", "test refresh failure")

    monkeypatch.setattr(transactions, "find_duplicates", fail_refresh)
    response = client.patch(f"/receipts/{a['id']}/ocr", headers=headers,
        json={"base_revision": a["revision"], "document": {"approval_number": "12345678"}})
    assert response.status_code == 400
    assert client.get(f"/receipts/{a['id']}", headers=headers).json() == before


def test_duplicate_insert_conflict_keeps_existing_decision_and_unique_pair(client, setup_transactions, monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import select
    from app.core.database import get_session
    from app.main import app
    from app.receipts.models import Receipt, ReconciliationIssue
    from app.receipts.transactions import find_duplicates
    headers, upload, _ = setup_transactions
    a, b = upload(), upload()
    issue = client.get("/reconciliation/issues", headers=headers).json()[0]
    assert client.post(f"/reconciliation/issues/{issue['id']}/resolve", headers=headers, json={"action": "SEPARATE"}).status_code == 200
    generator = app.dependency_overrides[get_session]()
    session = next(generator)
    try:
        receipt = session.get(Receipt, a["id"])
        execute = session.exec

        def missed_lookup(statement, *args, **kwargs):
            if "FROM reconciliation_issues" in str(statement):
                return SimpleNamespace(first=lambda: None)
            return execute(statement, *args, **kwargs)

        # A concurrent insert can commit after the lookup misses the row; exercise the conflict branch.
        with monkeypatch.context() as local_patch:
            local_patch.setattr(session, "exec", missed_lookup)
            find_duplicates(session, receipt)
            session.commit()
        rows = session.exec(select(ReconciliationIssue)).all()
        assert len(rows) == 1 and rows[0].id == issue["id"]
        assert rows[0].resolved and rows[0].active and rows[0].action == "SEPARATE"
        session.add(ReconciliationIssue(user_id=receipt.user_id, receipt_id=a["id"], candidate_receipt_id=b["id"], reason="SIMILAR_IMAGE"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert len(session.exec(select(ReconciliationIssue)).all()) == 1
    finally:
        generator.close()


def test_legacy_hash_backfill_preserves_facts_skips_missing_images_and_respects_owner(client, setup_transactions, monkeypatch):
    import uuid
    from sqlmodel import select
    from app.core.database import get_session
    from app.main import app
    from app.receipts import service
    from app.receipts.models import Receipt, ReconciliationIssue
    from app.receipts.fingerprints import backfill_image_fingerprints
    headers, upload, _ = setup_transactions
    monkeypatch.setattr(service, "image_fingerprints", lambda _: (None, None))
    a, b, missing = upload(), upload(), upload()
    foreign = client.post('/receipts', headers=auth_headers(client, 'backfill-other@example.com'),
        files={'file': ('receipt.png', PNG_BYTES, 'image/png')}).json()
    service.storage.delete(missing['image_url'])
    generator = app.dependency_overrides[get_session]()
    session = next(generator)
    try:
        owner = uuid.UUID(a['user_id'])
        before = {r.id: r.model_dump(mode='json', exclude={'file_hash', 'perceptual_hash'}) for r in session.exec(select(Receipt)).all()}
        result = backfill_image_fingerprints(session, service.storage, user_id=owner)
        session.commit()
        assert result['updated_count'] == 2 and result['updated_receipt_ids'] == [a['id'], b['id']]
        assert result['skipped'][0]['receipt_id'] == missing['id'] and result['skipped'][0]['reason'] == 'IMAGE_UNAVAILABLE'
        after = {r.id: r.model_dump(mode='json', exclude={'file_hash', 'perceptual_hash'}) for r in session.exec(select(Receipt)).all()}
        assert before == after
        assert session.get(Receipt, foreign['id']).file_hash is None
        issues = session.exec(select(ReconciliationIssue)).all()
        assert len(issues) == 1 and issues[0].reason == 'SAME_FILE' and not issues[0].resolved
        assert backfill_image_fingerprints(session, service.storage, user_id=owner)['updated_count'] == 0
        session.commit()
        assert len(session.exec(select(ReconciliationIssue)).all()) == 1
        mismatch = session.get(Receipt, a['id'])
        mismatch.file_hash = 'previous-source-hash'; mismatch.perceptual_hash = None
        session.add(mismatch); session.commit()
        result = backfill_image_fingerprints(session, service.storage, user_id=owner)
        assert result['updated_count'] == 0 and any(row['reason'] == 'SOURCE_HASH_MISMATCH' for row in result['skipped'])
        assert session.get(Receipt, a['id']).file_hash == 'previous-source-hash'
    finally:
        generator.close()


def test_evidence_link_supports_multiple_documents_without_reconciliation_decision(client, setup_transactions):
    headers, upload, confirm = setup_transactions
    a, b = confirm(upload()), confirm(upload())
    assert client.post(f"/transactions/{a['transaction_id']}/evidence", headers=headers, json={
        "receipt_id": b["id"], "base_revision": 1, "receipt_revision": b["revision"]}).status_code == 409
    response = client.post(f"/transactions/{a['transaction_id']}/evidence", headers=headers, json={
        "receipt_id": b["id"], "base_revision": 1, "receipt_revision": b["revision"], "source_transaction_revision": 1})
    assert response.status_code == 200
    assert len(response.json()["receipts"]) == 2
    assert len(response.json()["canonical_line_items"]) == 1


@pytest.mark.parametrize("source_already_linked", [False, True])
def test_manual_adjustment_accepts_confirmed_evidence_once_and_preserves_remaining_cap(client, setup_transactions, source_already_linked):
    headers, upload, confirm = setup_transactions
    original = confirm(upload())
    original_id = original["transaction_id"]
    draft_response = client.post(f"/transactions/{original_id}/adjustments", headers=headers, json={
        "base_revision": 1, "adjustment_type": "RETURN", "supply_date": "2026-10-05",
        "taxable_supply_amount": -1000, "tax_exempt_amount": 0, "vat_amount": -100, "total_amount": -1100})
    assert draft_response.status_code == 201
    draft = draft_response.json()
    refund = upload()
    saved = client.patch(f"/receipts/{refund['id']}/ocr", headers=headers, json={"base_revision": refund["revision"],
        "document": {"adjustment_type": "RETURN"}, "amount": -1100, "taxable_supply_amount": -1000,
        "vat_amount": -100, "tax_exempt_amount": 0, "transaction_amount": -1100,
        "line_items": [{"id": refund["line_items"][0]["id"], "name": "반품 상품", "quantity": -1,
                        "printed_unit_price": 1100, "line_amount": -1100}]}).json()
    refund = confirm(saved)
    source_id = refund["transaction_id"]
    original_revision, source_revision = 2, 1
    if source_already_linked:
        result = client.patch(f"/transactions/{source_id}", headers=headers, json={"base_revision": 1,
            "original_transaction_id": original_id, "original_revision": 2})
        assert result.status_code == 200
        source_revision, original_revision = 2, 3
    payload = {"receipt_id": refund["id"], "receipt_revision": refund["revision"], "base_revision": draft["revision"],
        "source_transaction_revision": source_revision, "original_revision": original_revision}
    path = f"/transactions/{draft['id']}/evidence"
    assert client.post(path, headers=headers, json={**payload, "original_revision": original_revision - 1}).status_code == 409
    assert client.get(f"/transactions/{draft['id']}", headers=headers).json()["revision"] == 1
    assert client.get(f"/transactions/{source_id}", headers=headers).json()["revision"] == source_revision
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    linked = response.json()
    assert linked["workflow_status"] == "NEEDS_CONTEXT" and linked["facts"]["ocr_confirmed"] is True
    assert linked["facts"]["total_amount"] == -1100 and linked["tax_analysis_confirmed"] is False
    assert linked["original_transaction_id"] == original_id
    assert linked["canonical_receipt_id"] == refund["id"]
    assert linked["canonical_line_items"][0]["line_amount"] == -1100
    assert linked["receipts"][0]["revision"] == refund["revision"] + 1
    assert client.get(f"/transactions/{source_id}", headers=headers).json()["workflow_status"] == "MERGED"
    # Repeating an already-linked request with current versions changes no totals or revisions.
    repeated = client.post(path, headers=headers, json={**payload, "base_revision": linked["revision"],
        "receipt_revision": linked["receipts"][0]["revision"]})
    assert repeated.status_code == 200 and repeated.json()["revision"] == linked["revision"]
    next_refund = client.post(f"/transactions/{original_id}/adjustments", headers=headers, json={
        "base_revision": original_revision + 1, "adjustment_type": "RETURN", "supply_date": "2026-10-05", "total_amount": -9900})
    assert next_refund.status_code == 201, next_refund.text
    outsider = auth_headers(client, "adjustment-evidence-outsider@example.com")
    assert client.post(path, headers=outsider, json=payload).status_code == 404


@pytest.mark.parametrize("change", ["amount", "type", "merchant", "date"])
def test_adjustment_evidence_mismatch_is_atomic(client, setup_transactions, change):
    headers, upload, confirm = setup_transactions
    original = confirm(upload())
    draft = client.post(f"/transactions/{original['transaction_id']}/adjustments", headers=headers, json={
        "base_revision": 1, "adjustment_type": "RETURN", "supply_date": "2026-10-05", "total_amount": -1100}).json()
    receipt = upload()
    total = -2200 if change == "amount" else -1100
    patch = {"base_revision": receipt["revision"], "document": {"adjustment_type": "CANCELLATION" if change == "type" else "RETURN"},
        "amount": total, "transaction_amount": total, "taxable_supply_amount": total / 1.1,
        "vat_amount": -200 if change == "amount" else -100, "tax_exempt_amount": 0}
    patch["taxable_supply_amount"] = -2000 if change == "amount" else -1000
    if change == "merchant": patch["business_number"] = "9999999999"
    if change == "date": patch["date"] = "2026-10-04"
    receipt = confirm(client.patch(f"/receipts/{receipt['id']}/ocr", headers=headers, json=patch).json())
    response = client.post(f"/transactions/{draft['id']}/evidence", headers=headers, json={
        "receipt_id": receipt["id"], "receipt_revision": receipt["revision"], "base_revision": 1,
        "source_transaction_revision": 1, "original_revision": 2})
    assert response.status_code == 409
    assert client.get(f"/transactions/{draft['id']}", headers=headers).json()["revision"] == 1
    assert client.get(f"/transactions/{receipt['transaction_id']}", headers=headers).json()["workflow_status"] == "UNRESOLVED_ADJUSTMENT"
    assert client.get(f"/receipts/{receipt['id']}", headers=headers).json()["revision"] == receipt["revision"]


@pytest.mark.parametrize("via_issue", [False, True])
def test_merging_originals_moves_refunds_atomically_and_preserves_cap(client, setup_transactions, via_issue):
    headers, upload, confirm = setup_transactions
    a, b = confirm(upload()), confirm(upload())
    a_id, b_id = a["transaction_id"], b["transaction_id"]
    adjustment = client.post(f"/transactions/{b_id}/adjustments", headers=headers, json={
        "base_revision": 1, "adjustment_type": "RETURN", "supply_date": "2026-10-05", "total_amount": -1100}).json()
    issue = client.get("/reconciliation/issues", headers=headers).json()[0]
    if via_issue:
        path = f"/reconciliation/issues/{issue['id']}/resolve"
        payload = {"action": "MERGE", "canonical_transaction_id": a_id,
            "transaction_revisions": {a_id: 1, b_id: 2}, "receipt_revisions": {str(b["id"]): b["revision"]}}
        revisions_key = "transaction_revisions"
    else:
        path = f"/transactions/{a_id}/evidence"
        payload = {"base_revision": 1, "receipt_id": b["id"], "receipt_revision": b["revision"],
            "source_transaction_revision": 2, "related_transaction_revisions": {}}
        revisions_key = "related_transaction_revisions"
    # A client must acknowledge the refund whose original link will be moved.
    for versions in ({}, {adjustment["id"]: 2}):
        candidate = {**payload, revisions_key: {**payload[revisions_key], **versions}}
        response = client.post(path, headers=headers, json=candidate)
        assert response.status_code == 409
        assert client.get(f"/transactions/{a_id}", headers=headers).json()["revision"] == 1
        assert client.get(f"/transactions/{b_id}", headers=headers).json()["revision"] == 2
        current = client.get(f"/transactions/{adjustment['id']}", headers=headers).json()
        assert current["original_transaction_id"] == b_id and current["revision"] == 1
        assert client.get(f"/receipts/{b['id']}", headers=headers).json()["transaction_id"] == b_id
        if via_issue:
            assert client.get("/reconciliation/issues", headers=headers).json()[0]["resolved"] is False
    payload[revisions_key][adjustment["id"]] = 1
    stale = {**payload}
    if via_issue:
        stale["receipt_revisions"] = {str(b["id"]): b["revision"] - 1}
    else:
        stale["receipt_revision"] = b["revision"] - 1
    assert client.post(path, headers=headers, json=stale).status_code == 409
    current = client.get(f"/transactions/{adjustment['id']}", headers=headers).json()
    assert current["original_transaction_id"] == b_id and current["revision"] == 1
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    moved = client.get(f"/transactions/{adjustment['id']}", headers=headers).json()
    assert moved["original_transaction_id"] == a_id and moved["revision"] == 2
    assert moved["facts"] == adjustment["facts"]
    assert client.get(f"/transactions/{b_id}", headers=headers).json()["workflow_status"] == "MERGED"
    canonical = client.get(f"/transactions/{a_id}", headers=headers).json()
    assert len(canonical["receipts"]) == 2 and len(canonical["canonical_line_items"]) == 1
    remaining = client.post(f"/transactions/{a_id}/adjustments", headers=headers, json={
        "base_revision": canonical["revision"], "adjustment_type": "RETURN", "supply_date": "2026-10-05", "total_amount": -9900})
    assert remaining.status_code == 201, remaining.text
    revision = client.get(f"/transactions/{a_id}", headers=headers).json()["revision"]
    assert client.post(f"/transactions/{a_id}/adjustments", headers=headers, json={
        "base_revision": revision, "adjustment_type": "RETURN", "supply_date": "2026-10-05", "total_amount": -1}).status_code == 409


def test_original_merge_rejects_combined_excess_refunds_without_changing_links(client, setup_transactions):
    headers, upload, confirm = setup_transactions
    a, b = confirm(upload()), confirm(upload())
    adjustments = []
    for receipt in (a, b):
        response = client.post(f"/transactions/{receipt['transaction_id']}/adjustments", headers=headers, json={
            "base_revision": 1, "adjustment_type": "RETURN", "supply_date": "2026-10-05", "total_amount": -6000})
        assert response.status_code == 201
        adjustments.append(response.json())
    response = client.post(f"/transactions/{a['transaction_id']}/evidence", headers=headers, json={
        "base_revision": 2, "receipt_id": b["id"], "receipt_revision": b["revision"], "source_transaction_revision": 2,
        "related_transaction_revisions": {row["id"]: row["revision"] for row in adjustments}})
    assert response.status_code == 409
    for receipt, adjustment in zip((a, b), adjustments):
        assert client.get(f"/transactions/{receipt['transaction_id']}", headers=headers).json()["revision"] == 2
        current = client.get(f"/transactions/{adjustment['id']}", headers=headers).json()
        assert current["revision"] == 1 and current["original_transaction_id"] == receipt["transaction_id"]
