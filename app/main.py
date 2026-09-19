from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.common.exceptions import register_exception_handlers
from app.deduction.router import router as deduction_router
from app.receipts.router import router as receipts_router

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
app.include_router(receipts_router)
app.include_router(deduction_router)
