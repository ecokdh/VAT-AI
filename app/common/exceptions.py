from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """api-spec.md §1.3 공통 에러 응답 포맷을 만들기 위한 예외.

    사용 예: raise AppError(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    """

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
