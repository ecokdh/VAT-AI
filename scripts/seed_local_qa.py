"""Create isolated, clearly labelled local QA fixtures. Never calls OCR/NTS/LLM."""
from datetime import date
from io import BytesIO

from PIL import Image, ImageDraw
from sqlmodel import Session, select

from app.auth.models import User
from app.core.config import settings
from app.core.database import engine
from app.core.security import hash_password
from app.receipts.models import Receipt
from app.receipts.service import storage
from app.transactions.service import create_from_receipt, confirm_transaction
from app.transactions.schemas import TransactionCreate


def main():
    if not settings.DB_URL.startswith("sqlite:"):
        raise SystemExit("QA fixtures are only allowed in local SQLite.")
    with Session(engine) as session:
        if session.exec(select(User).where(User.email == "local-qa@example.com")).first():
            print("QA account already exists; no data changed.")
            return
        user = User(email="local-qa@example.com", name="QA 테스트", password_hash=hash_password("Local-QA-2026!"))
        session.add(user)
        session.commit()
        session.refresh(user)
        for index in range(1, 9):
            direction = "sales" if index == 8 else "purchase"
            image = Image.new("RGB", (500, 650), "white")
            draw = ImageDraw.Draw(image)
            draw.text((40, 40), f"VAT-AI QA FIXTURE #{index}\nSYNTHETIC RECEIPT\n2026-09-{index:02}\nTOTAL: 11,000 KRW\nNot an actual receipt", fill="black", spacing=18)
            output = BytesIO()
            image.save(output, format="PNG")
            stored = storage.save(user.id, output.getvalue(), "image/png", "png")
            receipt = Receipt(user_id=user.id, image_url=stored.key, direction=direction, status="done",
                              vendor=f"QA 테스트 거래처 {index}", amount=11000, date=date(2026, 9, index),
                              ocr_raw="QA synthetic extraction fixture", processing_progress=100,
                              extraction_confirmed=index <= 6, ocr_pipeline_name="qa-fixture")
            session.add(receipt)
            session.commit()
            session.refresh(receipt)
            if index <= 6:
                transaction = create_from_receipt(session, user.id, receipt.id, TransactionCreate(
                    direction=direction, transaction_date=receipt.date, vendor=receipt.vendor,
                    description=f"26/09/{index:02} QA 불고기 {index}", total_amount=11000,
                    supply_amount=10000, vat_amount=1000, evidence_type="card_receipt",
                    business_related=True, tax_treatment="standard",
                ))
                confirm_transaction(session, user.id, transaction.id)
        print("Created QA account and 8 synthetic receipt fixtures (6 confirmed, 2 awaiting review).")


if __name__ == "__main__":
    main()
