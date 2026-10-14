from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """.env 기반 설정.

    기본값은 키가 없는 로컬 테스트를 위한 값이다. 운영에서는 DB_URL과
    JWT_SECRET을 반드시 실제 값으로 덮어써야 한다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
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
    # RAG 법령 임베딩. 차원(1536)은 law_embeddings.embedding 컬럼과 맞춰야 한다.
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    # 비어 있으면 /rag/embed 관리자 라우트가 모든 요청을 거부한다.
    ADMIN_API_KEY: str = ""
    # 국가법령정보 공동활용 API 인증키(OC). 법령 수집 스크립트(app.deduction.rag.fetch_laws)가 쓴다.
    LAW_OC: str = ""
    DEDUCTION_ANALYZER: str = ""
    NTS_BUSINESS_API_KEY: str = ""
    NTS_BUSINESS_API_URL: str = "https://api.odcloud.kr/api/nts-businessman/v1/status"
    NTS_BUSINESS_TIMEOUT_SECONDS: float = 10.0

    # CLOVA_API_KEY는 최초 스켈레톤의 이름과 호환하기 위한 fallback이다.
    CLOVA_API_KEY: str = ""
    CLOVA_OCR_API_URL: str = ""
    CLOVA_OCR_SECRET_KEY: str = ""
    OCR_PIPELINE: str = ""

    STORAGE_DIR: str = "storage"
    S3_BUCKET: str = ""
    AWS_REGION: str = "ap-northeast-2"
    PDFKIT_WKHTMLTOPDF_PATH: str = ""
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    MAX_IMAGE_PIXELS: int = 25_000_000
    CLOVA_TIMEOUT_SECONDS: float = 10.0


settings = Settings()
