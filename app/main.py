from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlmodel import Session


from app.auth.router import router as auth_router
from app.business.router import router as business_router
from app.common.exceptions import register_exception_handlers
from app.core.database import get_session
from app.deduction.router import router as deduction_router
from app.receipts.router import router as receipts_router
from app.receipts.transactions import router as transactions_router

app = FastAPI(title="VAT-AI")

# TODO: 프론트 실제 배포 도메인이 정해지면 allow_origins를 그걸로 좁힌다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(business_router)
app.include_router(receipts_router)
app.include_router(transactions_router)
app.include_router(deduction_router)

@app.get("/health", tags=["health"])
def health_check(db: Session = Depends(get_session)):
    db.exec(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
