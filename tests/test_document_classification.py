"""Tests for Unsupported Document Guide and Photo Quality Retake Guide."""
import json
import uuid
from datetime import date
import pytest
from sqlmodel import Session, select

from app.common.exceptions import AppException
from app.core.config import settings
from app.core.database import engine
from app.auth.models import User
from app.receipts.models import Receipt
from app.receipts import luna_client, service as receipt_service
from app.receipts.luna_low_contract import normalize, evaluate_classification
from app.receipts.storage import LocalFileStorage
from app.ocr_pipeline.contract import OcrPipelineInput, OcrStageUpdate
from app.ocr_pipeline.luna import LunaLowPipeline
from app.jobs.models import AsyncJob
from app.jobs.worker import process_async_job


@pytest.fixture(autouse=True)
def isolated_classification_database(tmp_path, monkeypatch):
    """Direct Session(engine) tests and their HTTP requests share a temporary DB."""
    from sqlmodel import SQLModel, create_engine
    from app.main import app
    from app.core.database import get_session
    import sys
    test_engine = create_engine(f"sqlite:///{tmp_path / 'classification.db'}", connect_args={'check_same_thread':False})
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(sys.modules[__name__], 'engine', test_engine)
    with Session(test_engine) as db:
        db.add(User(email='classification-fixture@example.com',password_hash='unused',name='테스트 계정'))
        db.commit()
    def session_override():
        with Session(test_engine) as db:
            yield db
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = session_override
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_session,None)
        else:
            app.dependency_overrides[get_session] = previous
        test_engine.dispose()


def make_raw_payload(c=None, h=None, m=None, i=None, uncertain=None):
    if c is None:
        c = {
            'doc_type': 'printed_receipt',
            'support_status': 'supported',
            'issues': [],
            'affected_regions': [],
            'readable_summary': '검토상점 11,000원 결제',
            'reasoning': '선명한 인쇄 구매 영수증',
        }
    if h is None:
        h = {'vendor': '검토상점', 'branch': '강남점', 'business_number': '123-45-67890', 'datetime': '2026-10-15 12:00:00'}
    if m is None:
        m = [
            {'role': 'supply', 'scope': 'taxable', 'label': '공급가액', 'value': 10000},
            {'role': 'vat', 'scope': 'taxable', 'label': '부가세', 'value': 1000},
            {'role': 'total', 'scope': 'all', 'label': '합계', 'value': 11000},
            {'role': 'payment', 'scope': 'unknown', 'label': '카드결제', 'value': 11000},
        ]
    if i is None:
        i = [{'n': '아메리카노', 'q': 2, 'u': 5000, 'p': 10000, 't': 'item', 'parent': None}]
    if uncertain is None:
        uncertain = []
    return {'c': c, 'h': h, 'm': m, 'i': i, 'uncertain': uncertain}


def test_normal_printed_receipt_supported():
    raw = make_raw_payload()
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'completed'
    assert clf['doc_type'] == 'printed_receipt'
    assert clf['support_status'] == 'supported'
    assert clf['issue_code'] == 'NORMAL_COMPLETED'
    assert clf['guide_message'] is None


def test_normal_receipt_without_vat_or_biz_number_not_rejected():
    """Missing VAT or business number alone must NOT reject a printed receipt."""
    h = {'vendor': '간이식당', 'branch': None, 'business_number': None, 'datetime': '2026-10-15 13:00:00'}
    m = [{'role': 'payment', 'scope': 'unknown', 'label': '합계', 'value': 8000}]
    i = [{'n': '백반', 'q': 1, 'u': 8000, 'p': 8000, 't': 'item', 'parent': None}]
    # Model incorrectly says other_document because VAT is missing
    c = {
        'doc_type': 'other_document',
        'support_status': 'unsupported',
        'issues': [],
        'affected_regions': [],
        'readable_summary': '간이식당 8000원',
        'reasoning': '부가세와 사업자등록번호가 없어 정규 영수증이 아니라고 판단',
    }
    raw = make_raw_payload(c=c, h=h, m=m, i=i)
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    # Do not reject or claim a proven category when the model's reason is inconsistent.
    assert clf['final_status'] == 'needs_edit'
    assert clf['doc_type'] == 'undetermined'
    assert clf['support_status'] == 'undetermined'
    assert clf['final_status'] != 'unsupported'


def test_tilted_receipt_readable_not_rejected():
    """Angled or dark photo that is readable must NOT be rejected."""
    c = {
        'doc_type': 'printed_receipt',
        'support_status': 'supported',
        'issues': [],
        'affected_regions': [],
        'readable_summary': '검토상점 11,000원 결제',
        'reasoning': '사진이 약 15도 기울어졌으나 글자와 숫자가 모두 선명함',
    }
    raw = make_raw_payload(c=c)
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'completed'
    assert clf['support_status'] == 'supported'


def test_handwritten_receipt_rejected_as_unsupported():
    """Handwritten receipt must be rejected with the exact guidance text."""
    c = {
        'doc_type': 'handwritten_receipt',
        'support_status': 'unsupported',
        'issues': [],
        'affected_regions': [],
        'readable_summary': '수기 영수증',
        'reasoning': '손글씨로 작성된 간이 영수증',
    }
    h = {'vendor': '수기상회', 'branch': None, 'business_number': None, 'datetime': None}
    m = [{'role': 'total', 'scope': 'all', 'label': '금액', 'value': 50000}]
    raw = make_raw_payload(c=c, h=h, m=m, i=[])
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'unsupported'
    assert clf['doc_type'] == 'handwritten_receipt'
    assert clf['support_status'] == 'unsupported'
    assert clf['issue_code'] == 'UNSUPPORTED_HANDWRITTEN'
    assert clf['guide_message'] == '현재는 인쇄된 구매 영수증만 지원합니다. 다른 영수증 사진을 선택해 주세요.'


def test_order_screen_rejected_as_unsupported():
    """Cart / order screen must be rejected with the exact guidance text."""
    c = {
        'doc_type': 'order_screen',
        'support_status': 'unsupported',
        'issues': [],
        'affected_regions': [],
        'readable_summary': '주문 화면',
        'reasoning': '모바일 장바구니 및 결제 주문 화면 캡처',
    }
    raw = make_raw_payload(c=c)
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'unsupported'
    assert clf['issue_code'] == 'UNSUPPORTED_ORDER_SCREEN'
    assert clf['guide_message'] == '현재는 인쇄된 구매 영수증만 지원합니다. 다른 영수증 사진을 선택해 주세요.'


def test_general_document_rejected_as_unsupported():
    """General documents like contracts or quotes must be rejected."""
    c = {
        'doc_type': 'other_document',
        'support_status': 'unsupported',
        'issues': [],
        'affected_regions': [],
        'readable_summary': '용역 계약서',
        'reasoning': '구매 영수증이 아닌 용역 계약서 양식',
    }
    h = {'vendor': '주식회사 계약', 'branch': None, 'business_number': None, 'datetime': None}
    raw = make_raw_payload(c=c, h=h, m=[], i=[])
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'unsupported'
    assert clf['issue_code'] == 'UNSUPPORTED_OTHER_DOCUMENT'
    assert clf['guide_message'] == '현재는 인쇄된 구매 영수증만 지원합니다. 다른 영수증 사진을 선택해 주세요.'


def test_glare_on_amount_triggers_retake():
    """Glare on amount section triggers specific glare retake guide."""
    c = {
        'doc_type': 'printed_receipt',
        'support_status': 'supported',
        'issues': ['glare'],
        'affected_regions': ['amount'],
        'readable_summary': '스타벅스 강남점',
        'reasoning': '합계 금액 부분에 강한 조명 반사가 있어 숫자를 읽을 수 없음',
    }
    h = {'vendor': '스타벅스', 'branch': '강남점', 'business_number': '201-81-21515', 'datetime': '2026-10-15 14:00:00'}
    m = []  # amount unreadable
    raw = make_raw_payload(c=c, h=h, m=m)
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'retake'
    assert clf['issue_code'] == 'RETAKE_GLARE_AMOUNT'
    assert clf['guide_message'] == '금액 부분에 빛이 반사되어 읽기 어렵습니다. 빛 반사를 피해 다시 촬영해 주세요.'


def test_cut_off_bottom_triggers_retake():
    """Cut off at bottom triggers cut-off retake guide."""
    c = {
        'doc_type': 'printed_receipt',
        'support_status': 'supported',
        'issues': ['cut_off'],
        'affected_regions': ['amount', 'items'],
        'readable_summary': '상호만 보임',
        'reasoning': '영수증 하단 결제액 영역이 프레임 밖으로 잘림',
    }
    h = {'vendor': '이마트', 'branch': '역삼점', 'business_number': '101-81-12345', 'datetime': None}
    m = []
    raw = make_raw_payload(c=c, h=h, m=m, i=[])
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'retake'
    assert clf['issue_code'] == 'RETAKE_CUT_OFF_AMOUNT'
    assert clf['guide_message'] == '금액 영역이 잘려 읽기 어렵습니다. 영수증 전체가 나오도록 다시 촬영해 주세요.'


def test_blur_triggers_retake():
    """Blur making core fields unreadable triggers blur retake guide."""
    c = {
        'doc_type': 'printed_receipt',
        'support_status': 'supported',
        'issues': ['blur'],
        'affected_regions': ['vendor', 'amount', 'date'],
        'readable_summary': None,
        'reasoning': '카메라 초점이 빗나가 모든 텍스트가 심하게 흐림',
    }
    h = {'vendor': None, 'branch': None, 'business_number': None, 'datetime': None}
    m = []
    raw = make_raw_payload(c=c, h=h, m=m, i=[])
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'retake'
    assert clf['issue_code'] == 'RETAKE_BLUR'
    assert clf['guide_message'] == '사진이 흐려 글자를 읽기 어렵습니다. 초점을 맞추어 다시 촬영해 주세요.'


def test_heavy_distortion_triggers_retake():
    """Heavy distortion making receipt unreadable triggers distortion retake guide."""
    c = {
        'doc_type': 'printed_receipt',
        'support_status': 'supported',
        'issues': ['heavy_distortion'],
        'affected_regions': ['amount', 'vendor'],
        'readable_summary': None,
        'reasoning': '영수증이 심하게 구겨져 글자 선형성을 확인할 수 없음',
    }
    h = {'vendor': None, 'branch': None, 'business_number': None, 'datetime': None}
    m = []
    raw = make_raw_payload(c=c, h=h, m=m, i=[])
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'retake'
    assert clf['issue_code'] == 'RETAKE_HEAVY_DISTORTION'
    assert clf['guide_message'] == '사진 왜곡이 심해 정보를 판독하기 어렵습니다. 영수증을 평평하게 펴고 정면에서 다시 촬영해 주세요.'


def test_partial_field_unreadable_goes_to_review():
    """Supported receipt with minor missing field goes to review (needs_edit)."""
    h = {'vendor': '편의점', 'branch': None, 'business_number': None, 'datetime': None}  # date missing
    m = [{'role': 'payment', 'scope': 'unknown', 'label': '카드', 'value': 3500}]
    i = [{'n': '생수', 'q': 1, 'u': 3500, 'p': 3500, 't': 'item', 'parent': None}]
    c = {
        'doc_type': 'printed_receipt',
        'support_status': 'supported',
        'issues': [],
        'affected_regions': ['date'],
        'readable_summary': '편의점 3,500원',
        'reasoning': '거래일시 부분이 잉크 번짐으로 흐림',
    }
    raw = make_raw_payload(c=c, h=h, m=m, i=i)
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'needs_edit'
    assert clf['support_status'] == 'supported'
    assert clf['guide_message'] is None


def test_undetermined_with_usable_data_goes_to_review():
    """Undetermined document type with usable transaction data goes to review."""
    c = {
        'doc_type': 'undetermined',
        'support_status': 'undetermined',
        'issues': [],
        'affected_regions': [],
        'readable_summary': '카페 5000원',
        'reasoning': '문서 형태가 다소 특이하나 거래처와 결제액이 명확함',
    }
    h = {'vendor': '골목카페', 'branch': None, 'business_number': None, 'datetime': '2026-10-15 11:00:00'}
    m = [{'role': 'payment', 'scope': 'unknown', 'label': '결제액', 'value': 5000}]
    raw = make_raw_payload(c=c, h=h, m=m)
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'needs_edit'
    assert clf['issue_code'] == 'UNDETERMINED_WITH_DATA'


def test_undetermined_without_usable_data_guides_reason():
    """Undetermined document type without usable data guides with clear reason."""
    c = {
        'doc_type': 'undetermined',
        'support_status': 'undetermined',
        'issues': [],
        'affected_regions': [],
        'readable_summary': None,
        'reasoning': '문서 종류를 알 수 없고 거래 내용도 없음',
    }
    h = {'vendor': None, 'branch': None, 'business_number': None, 'datetime': None}
    raw = make_raw_payload(c=c, h=h, m=[], i=[])
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['final_status'] == 'needs_edit'
    assert clf['support_status'] == 'undetermined'
    assert clf['issue_code'] == 'UNDETERMINED_NO_DATA'


def test_legacy_response_marked_uninspected():
    """Past stored responses without 'c' must be marked as uninspected."""
    raw = {
        'h': {'vendor': '과거상점', 'branch': None, 'business_number': None, 'datetime': '2026-10-10 10:00:00'},
        'm': [{'role': 'payment', 'scope': 'unknown', 'label': '결제', 'value': 10000}],
        'i': [{'n': '과거상품', 'q': 1, 'u': 10000, 'p': 10000, 't': 'item', 'parent': None}],
        'uncertain': [],
    }
    norm = luna_client.checked_normalize(raw)
    clf = norm['classification']
    assert clf['doc_type'] == 'uninspected'
    assert clf['support_status'] == 'uninspected'
    assert clf['final_status'] in ('completed', 'needs_edit')
    assert clf['final_status'] != 'unsupported'


def test_pipeline_and_worker_integration(tmp_path, monkeypatch):
    """End-to-end integration through pipeline and worker for unsupported and retake."""
    with Session(engine) as session:
        user = session.exec(select(User)).first()
        if not user:
            user = User(email="test_clf@example.com", hashed_password="pw", role="user")
            session.add(user)
            session.commit()
            session.refresh(user)

        storage = LocalFileStorage(tmp_path)
        stored = storage.save(user.id, b"fake-image-bytes", "image/jpeg", "jpg")
        monkeypatch.setattr(receipt_service, "storage", storage)

        # 1. Unsupported receipt job
        r_unsupported = Receipt(user_id=user.id, image_url=stored.key, status="processing")
        session.add(r_unsupported)
        session.flush()
        job1 = AsyncJob(user_id=user.id, job_type="ocr", payload_json=json.dumps({"receipt_id": r_unsupported.id}))
        session.add(job1)
        session.commit()

        handwritten_raw = make_raw_payload(
            c={
                'doc_type': 'handwritten_receipt',
                'support_status': 'unsupported',
                'issues': [],
                'affected_regions': [],
                'readable_summary': '수기 간이영수증',
                'reasoning': '손글씨로 작성된 간이영수증',
            },
            h={'vendor': '수기집', 'branch': None, 'business_number': None, 'datetime': None},
            m=[{'role': 'payment', 'scope': 'unknown', 'label': '금액', 'value': 20000}],
            i=[],
        )
        monkeypatch.setattr(settings, 'OCR_PIPELINE', 'app.ocr_pipeline.luna:create_pipeline')
        import hashlib
        img_sha = hashlib.sha256(b"fake-image-bytes").hexdigest()
        async def mock_recognize(*args):
            return {
                'engine': 'luna_low',
                'document': normalize(handwritten_raw),
                'image_sha256': img_sha,
                'confirmed': False,
            }
        monkeypatch.setattr(luna_client, 'recognize', mock_recognize)

        process_async_job(session, job1)
        session.commit()
        session.refresh(r_unsupported)

        assert r_unsupported.status == "unsupported"
        assert r_unsupported.doc_type == "handwritten_receipt"
        assert r_unsupported.support_status == "unsupported"
        assert r_unsupported.issue_code == "UNSUPPORTED_HANDWRITTEN"
        assert r_unsupported.guide_message == "현재는 인쇄된 구매 영수증만 지원합니다. 다른 영수증 사진을 선택해 주세요."
        assert r_unsupported.stage_statuses["transaction_extraction"] == "failed"

        # 2. Retake receipt job
        r_retake = Receipt(user_id=user.id, image_url=stored.key, status="processing")
        session.add(r_retake)
        session.flush()
        job2 = AsyncJob(user_id=user.id, job_type="ocr", payload_json=json.dumps({"receipt_id": r_retake.id}))
        session.add(job2)
        session.commit()

        glare_raw = make_raw_payload(
            c={
                'doc_type': 'printed_receipt',
                'support_status': 'supported',
                'issues': ['glare'],
                'affected_regions': ['amount'],
                'readable_summary': '상호만 보임',
                'reasoning': '금액 영역 빛 반사',
            },
            h={'vendor': '빛반사마트', 'branch': None, 'business_number': None, 'datetime': '2026-10-15 15:00:00'},
            m=[],
            i=[],
        )
        async def mock_recognize_glare(*args):
            return {
                'engine': 'luna_low',
                'document': normalize(glare_raw),
                'image_sha256': img_sha,
                'confirmed': False,
            }
        monkeypatch.setattr(luna_client, 'recognize', mock_recognize_glare)

        process_async_job(session, job2)
        session.commit()
        session.refresh(r_retake)

        assert r_retake.status == "retake"
        assert r_retake.doc_type == "printed_receipt"
        assert r_retake.support_status == "supported"
        assert r_retake.issue_code == "RETAKE_GLARE_AMOUNT"
        assert r_retake.guide_message == "금액 부분에 빛이 반사되어 읽기 어렵습니다. 빛 반사를 피해 다시 촬영해 주세요."
        assert r_retake.stage_statuses["photo_quality"] == "failed"


def test_luna_failure_distinct_from_unsupported(tmp_path, monkeypatch):
    """Network/timeout/auth failure must be FAILED, not unsupported or retake."""
    with Session(engine) as session:
        user = session.exec(select(User)).first()
        storage = LocalFileStorage(tmp_path)
        stored = storage.save(user.id, b"fake-image", "image/jpeg", "jpg")
        monkeypatch.setattr(receipt_service, "storage", storage)

        receipt = Receipt(user_id=user.id, image_url=stored.key, status="processing")
        session.add(receipt)
        session.flush()
        job = AsyncJob(user_id=user.id, job_type="ocr", payload_json=json.dumps({"receipt_id": receipt.id}))
        session.add(job)
        session.commit()

        async def mock_timeout(*args):
            raise luna_client.LunaFailure("TIMEOUT")
        monkeypatch.setattr(luna_client, 'recognize', mock_timeout)
        monkeypatch.setattr(settings, 'OCR_PIPELINE', 'app.ocr_pipeline.luna:create_pipeline')

        process_async_job(session, job)
        session.commit()
        session.refresh(receipt)

        assert receipt.status == "failed"
        assert receipt.status != "unsupported"
        assert receipt.status != "retake"


def test_v2_receipt_api_returns_classification_fields_and_isolation():
    """Verify GET /v2/receipts/{id} returns classification and respects user isolation."""
    from starlette.testclient import TestClient
    from app.main import app
    from app.core.security import create_access_token

    client = TestClient(app)
    with Session(engine) as session:
        user_a = session.exec(select(User).where(User.email == "user_a_clf@example.com")).first()
        if not user_a:
            user_a = User(email="user_a_clf@example.com", password_hash="pw", name="사용자A")
            session.add(user_a)
            session.commit()
            session.refresh(user_a)

        user_b = session.exec(select(User).where(User.email == "user_b_clf@example.com")).first()
        if not user_b:
            user_b = User(email="user_b_clf@example.com", password_hash="pw", name="사용자B")
            session.add(user_b)
            session.commit()
            session.refresh(user_b)

        receipt = Receipt(
            user_id=user_a.id,
            image_url="dummy.jpg",
            status="unsupported",
            doc_type="handwritten_receipt",
            support_status="unsupported",
            readability_issues_json=json.dumps([]),
            affected_regions_json=json.dumps([]),
            issue_code="UNSUPPORTED_HANDWRITTEN",
            guide_message="현재는 인쇄된 구매 영수증만 지원합니다. 다른 영수증 사진을 선택해 주세요.",
            classification_version="v2",
        )
        session.add(receipt)
        session.commit()
        session.refresh(receipt)
        token_a = create_access_token(user_a.id, user_a.email, user_a.token_version)
        token_b = create_access_token(user_b.id, user_b.email, user_b.token_version)
        receipt_id = receipt.id

    # 1. User A can view the receipt with classification fields
    res_a = client.get(f"/v2/receipts/{receipt_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["status"] == "unsupported"
    assert data_a["doc_type"] == "handwritten_receipt"
    assert data_a["support_status"] == "unsupported"
    assert data_a["issue_code"] == "UNSUPPORTED_HANDWRITTEN"
    assert data_a["guide_message"] == "현재는 인쇄된 구매 영수증만 지원합니다. 다른 영수증 사진을 선택해 주세요."
    assert data_a["classification_version"] == "v2"

    # 2. User B gets 404 (user isolation)
    res_b = client.get(f"/v2/receipts/{receipt_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 404


def test_new_upload_creates_new_isolated_receipt_job(tmp_path, monkeypatch):
    """Uploading a new photo connects to a new processing instance without reusing previous results."""
    from app.jobs.service import enqueue_receipt_ocr
    from io import BytesIO
    from PIL import Image
    import asyncio

    with Session(engine) as session:
        user = session.exec(select(User)).first()
        storage = LocalFileStorage(tmp_path)
        monkeypatch.setattr(receipt_service, "storage", storage)

        bio = BytesIO()
        Image.new("RGB", (10, 10), color=(255, 255, 255)).save(bio, format="PNG")
        png_bytes = bio.getvalue()

        job1, r1 = asyncio.run(enqueue_receipt_ocr(session, user.id, png_bytes, "image/png", "purchase"))
        job2, r2 = asyncio.run(enqueue_receipt_ocr(session, user.id, png_bytes, "image/png", "purchase"))

        assert r1.id != r2.id
        assert job1.id != job2.id
        assert r1.image_url != r2.image_url
