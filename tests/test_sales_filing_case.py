"""매출 집계(SalesFilingWorkflow)를 처음 여는 요청이 동시에 와도 500 없이 같은 행을 쓰는지."""
import uuid

from sqlmodel import Session, SQLModel, create_engine, func, select

from app.sales_filing.models import SalesFilingWorkflow
from app.sales_filing.service import _case


class NoRows:
    def first(self):
        return None


def test_case_reuses_row_created_by_concurrent_request(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    user_id = uuid.uuid4()
    with Session(engine) as other_request:  # 다른 요청이 먼저 만들어 커밋했다.
        existing = SalesFilingWorkflow(user_id=user_id, period="2026-H1")
        other_request.add(existing)
        other_request.commit()
        existing_id = existing.id

    with Session(engine) as session:
        real_exec, calls = session.exec, []

        def exec_seeing_no_row_first(statement):  # 이 요청은 그 직전에 조회해서 행이 없다고 본 상황
            calls.append(statement)
            return NoRows() if len(calls) == 1 else real_exec(statement)

        session.exec = exec_seeing_no_row_first
        case = _case(session, user_id, "2026-H1")
        session.commit()

        assert case.id == existing_id
        assert real_exec(select(func.count()).select_from(SalesFilingWorkflow)).one() == 1
