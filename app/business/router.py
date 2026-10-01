from fastapi import APIRouter

from app.business import service
from app.business.schemas import BusinessVerifyRequest, BusinessVerifyResponse

router = APIRouter(prefix="/business", tags=["business"])


@router.post("/verify", response_model=BusinessVerifyResponse)
def verify_business(data: BusinessVerifyRequest):
    return service.verify_business(data.business_number)
