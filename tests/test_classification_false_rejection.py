"""Independent regression cases for classification gates; no API calls."""
import pytest
from app.receipts.luna_low_contract import evaluate_classification

FIELDS={'vendor':'예시상점','payment_amount':11000,'printed_total_amount':11000,'transaction_datetime':'2026-10-15 12:00:00'}

def c(kind='printed_receipt',support='supported',issues=None,regions=None,reason='인쇄된 구매 영수증'):
    return {'doc_type':kind,'support_status':support,'issues':issues or [],'affected_regions':regions or [],'readable_summary':None,'reasoning':reason}

@pytest.mark.parametrize('problem',['glare','cut_off','blur','heavy_distortion'])
def test_readable_amount_is_not_rejected_by_photo_tag(problem):
    result=evaluate_classification(c(issues=[problem],regions=['amount']),FIELDS,[{'name':'상품'}],[],[])
    assert result['final_status']=='needs_edit'

def test_items_only_cutoff_preserves_readable_transaction():
    assert evaluate_classification(c(issues=['cut_off'],regions=['items']),FIELDS,[],[],[])['final_status']=='needs_edit'

@pytest.mark.parametrize('kind',['handwritten_receipt','order_screen','other_document'])
def test_conflicting_support_or_no_reason_does_not_hard_reject(kind):
    for classification in [c(kind,'supported',reason='지원하는 구매 영수증'),c(kind,'unsupported',reason='')]:
        assert evaluate_classification(classification,FIELDS,[],[],[])['final_status']=='needs_edit'

def test_undetermined_without_data_remains_undetermined():
    result=evaluate_classification(c('undetermined','undetermined',reason='문서 종류 확인 불가'),{},[],[],[])
    assert result['support_status']=='undetermined'
    assert result['final_status']=='needs_edit'

def test_glare_without_amount_region_does_not_invent_amount_damage():
    result=evaluate_classification(c(issues=['glare'],regions=['items']),{'vendor':'상점'},[],[],[])
    assert result['final_status']=='needs_edit'

def test_blur_amount_unreadable_even_when_vendor_survives():
    result=evaluate_classification(c(issues=['blur'],regions=['amount']),{'vendor':'상점'},[],[],[])
    assert result['final_status']=='retake'

def test_absent_tax_and_business_number_are_not_quality_failures():
    result=evaluate_classification(c(),FIELDS,[],[],[])
    assert result['final_status']=='completed'
