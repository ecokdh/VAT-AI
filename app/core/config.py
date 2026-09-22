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
    OPENAI_API_KEY: str = ""

    # CLOVA_API_KEY는 최초 스켈레톤의 이름과 호환하기 위한 fallback이다.
    CLOVA_API_KEY: str = ""
    CLOVA_OCR_API_URL: str = ""
    CLOVA_OCR_SECRET_KEY: str = ""

    STORAGE_DIR: str = "storage"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    MAX_IMAGE_PIXELS: int = 25_000_000
    CLOVA_TIMEOUT_SECONDS: float = 10.0


settings = Settings()
