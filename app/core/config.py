from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """.env 기반 설정. 필수 환경변수는 requirements.md / .env.example 참고."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DB_URL: str
    JWT_SECRET: str
    OPENAI_API_KEY: str
    CLOVA_API_KEY: str


settings = Settings()
