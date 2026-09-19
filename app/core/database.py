from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

# Alembic autogenerate가 모든 테이블을 찾으려면 각 모듈의 모델이 어딘가에서 import되어 있어야 한다.
# 새 모델을 추가하면 반드시 아래 import 목록에도 추가할 것.
from app.auth.models import User  # noqa: F401
from app.receipts.models import Receipt  # noqa: F401
from app.deduction.models import Deduction  # noqa: F401

engine = create_engine(settings.DB_URL)


def get_session():
    with Session(engine) as session:
        yield session

