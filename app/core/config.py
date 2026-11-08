from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """.env 기반 설정.

    기본값은 키가 없는 로컬 테스트를 위한 값이다. 운영에서는 DB_URL과
    JWT_SECRET을 반드시 실제 값으로 덮어써야 한다.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.luna.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DB_URL: str = "sqlite:///./vat_ai.db"
    JWT_SECRET: str = "local-dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    # A트랙 계약명에 맞춘 JWT 만료 시간 설정.
    JWT_EXPIRE_MINUTES: int = 60 * 24
    FRONTEND_URL: str = "http://localhost:5173"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USE_SSL: bool = False
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    ADMIN_API_KEY: str = ""
    LAW_OC: str = ""
    RECEIPT_RECOGNITION_BACKEND: str = "clova"
    LUNA_API_KEY_FILE: str = ""
    LUNA_TIMEOUT_SECONDS: float = 180.0
    LUNA_BUDGET_KRW: float = 2000.0
    LUNA_BUDGET_LEDGER_FILE: str = "storage/luna_budget.json"
    # photo_ocr: General OCR + image; photo: explicit legacy image-only mode.
    LUNA_INPUT_MODE: str = "photo_ocr"
    LOCAL_FRONTEND_ORIGIN: str = ""
    DEDUCTION_ANALYZER: str = ""
    NTS_BUSINESS_API_KEY: str = ""
    NTS_BUSINESS_API_URL: str = "https://api.odcloud.kr/api/nts-businessman/v1/status"
    NTS_BUSINESS_VALIDATE_URL: str = "https://api.odcloud.kr/api/nts-businessman/v1/validate"
    NTS_BUSINESS_TIMEOUT_SECONDS: float = 10.0

    # CLOVA_API_KEY는 최초 스켈레톤의 이름과 호환하기 위한 fallback이다.
    CLOVA_API_KEY: str = ""
    CLOVA_OCR_API_URL: str = ""
    CLOVA_OCR_SECRET_KEY: str = ""
    OCR_PIPELINE: str = ""

    @field_validator("OCR_PIPELINE")
    @classmethod
    def normalize_legacy_ocr_pipeline(cls, value: str) -> str:
        if value == "app.ocr_pipeline.luna:create_pipeline":
            return "app.receipts.ocr.luna:create_pipeline"
        return value
    # legacy keeps the current Luna low contract. relation_v1 is the experiment path.
    RECEIPT_STRUCTURE_PATH: str = "legacy"

    STORAGE_DIR: str = "storage"
    S3_BUCKET: str = ""
    AWS_REGION: str = "ap-northeast-2"
    PDFKIT_WKHTMLTOPDF_PATH: str = ""
    # 부가세 신고서(별지 제21호서식) 덧입히기용 한글 TTF. 비우면 맑은 고딕·나눔고딕을 찾는다.
    VAT_FORM_FONT: str = ""
    # 신고서 검증 모델 서버(training/serve.py) 주소. 비우면 검증 없이 PDF만 만든다.
    FORM_VERIFIER_URL: str = ""
    FORM_VERIFIER_TIMEOUT_SECONDS: float = 180.0
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    MAX_IMAGE_PIXELS: int = 25_000_000
    CLOVA_TIMEOUT_SECONDS: float = 10.0


settings = Settings()
