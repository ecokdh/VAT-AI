"""다른 트랙(receipts, deduction)이 그대로 import해서 쓰는 인증 의존성.

사용 예: def handler(user: User = Depends(get_current_user)): ...
"""

from fastapi import Depends
from fastapi.security import HTTPBearer

bearer_scheme = HTTPBearer()


def get_current_user(credentials=Depends(bearer_scheme)):
    raise NotImplementedError
    # TODO: core.security.decode_access_token으로 payload["sub"] 추출
    # -> users 테이블에서 조회, 없으면 AppError(401, "UNAUTHORIZED", ...)
