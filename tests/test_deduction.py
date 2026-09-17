import unittest
import uuid
from datetime import date
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine, select

from app.auth.models import User
from app.common.exceptions import AppError
from app.deduction.ai_client import DeductionJudgement
from app.deduction.models import Deduction
from app.deduction.service import analyze_receipt, get_report
from app.receipts.models import Receipt


class DeductionServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)
        self.user_id = uuid.uuid4()
        self.other_user_id = uuid.uuid4()

    def _receipt(self, **kwargs) -> Receipt:
        defaults = {
            "user_id": self.user_id,
            "image_url": "receipts/1.jpg",
            "ocr_raw": "업무용 음료 구매",
            "vendor": "카페 VAT",
            "amount": 4500.0,
            "date": date(2026, 9, 16),
            "status": "done",
        }
        defaults.update(kwargs)
        return Receipt(**defaults)

    def test_analyze_creates_and_updates_one_deduction(self):
        with Session(self.engine) as session:
            receipt = self._receipt()
            session.add(receipt)
            session.commit()
            session.refresh(receipt)

            first = DeductionJudgement(True, "업무 관련 지출", "복리후생비", 4500.0)
            second = DeductionJudgement(False, "개인 사용으로 재판정", "접대비", 0.0)

            with patch(
                "app.deduction.service.ai_client.judge_deduction",
                side_effect=[first, second],
            ):
                created = analyze_receipt(session, self.user_id, receipt.id)
                updated = analyze_receipt(session, self.user_id, receipt.id)

            deductions = session.exec(select(Deduction)).all()

            self.assertEqual(created.receipt_id, receipt.id)
            self.assertFalse(updated.is_deductible)
            self.assertEqual(len(deductions), 1)
            self.assertEqual(deductions[0].amount, 0.0)

    def test_analyze_rejects_other_users_receipt(self):
        with Session(self.engine) as session:
            receipt = self._receipt()
            session.add(receipt)
            session.commit()
            session.refresh(receipt)

            with self.assertRaises(AppError) as context:
                analyze_receipt(session, self.other_user_id, receipt.id)

            self.assertEqual(context.exception.status_code, 404)
            self.assertEqual(context.exception.code, "NOT_FOUND")

    def test_analyze_wraps_unexpected_ai_error(self):
        with Session(self.engine) as session:
            receipt = self._receipt()
            session.add(receipt)
            session.commit()
            session.refresh(receipt)

            with patch(
                "app.deduction.service.ai_client.judge_deduction",
                side_effect=RuntimeError("timeout"),
            ):
                with self.assertRaises(AppError) as context:
                    analyze_receipt(session, self.user_id, receipt.id)

            self.assertEqual(context.exception.status_code, 502)
            self.assertEqual(context.exception.code, "EXTERNAL_API_ERROR")

    def test_report_filters_by_user_month_and_deductible_status(self):
        with Session(self.engine) as session:
            current = self._receipt(date=date(2026, 9, 16), amount=4500.0)
            previous_month = self._receipt(date=date(2026, 8, 31), amount=7000.0)
            not_deductible = self._receipt(date=date(2026, 9, 17), amount=1200.0)
            other_user = self._receipt(
                user_id=self.other_user_id,
                date=date(2026, 9, 18),
                amount=9900.0,
            )

            session.add_all([current, previous_month, not_deductible, other_user])
            session.commit()

            for receipt, deductible, amount in [
                (current, True, 4500.0),
                (previous_month, True, 7000.0),
                (not_deductible, False, 1200.0),
                (other_user, True, 9900.0),
            ]:
                session.add(
                    Deduction(
                        receipt_id=receipt.id,
                        is_deductible=deductible,
                        reason="test",
                        category="test",
                        amount=amount,
                    )
                )

            session.commit()

            report = get_report(session, self.user_id, "2026-09")

            self.assertEqual(report.count, 1)
            self.assertEqual(report.total_amount, 4500.0)
            self.assertEqual(report.items[0].receipt_id, current.id)

    def test_report_rejects_invalid_period(self):
        with Session(self.engine) as session:
            with self.assertRaises(AppError) as context:
                get_report(session, self.user_id, "2026-9")

            self.assertEqual(context.exception.status_code, 400)
            self.assertEqual(context.exception.code, "VALIDATION_ERROR")