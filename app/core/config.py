from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "CodeZen"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True

    DATABASE_URL: str
    DATABASE_SYNC_URL: str

    REDIS_URL: str = "redis://localhost:6379/0"

    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8001

    GROQ_API_KEY: str
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "phi3:mini"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 7200  # 5 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 60

    INVITE_TOKEN_SECRET: str

    SIMILARITY_THRESHOLD: float = 0.85
    MAX_RETRIEVED_CHUNKS: int = 5
    LLM_TEMPERATURE: float = 0.1
    LLM_TOP_P: float = 0.85
    LLM_MAX_TOKENS: int = 512

    CHAT_HISTORY_TTL_SECONDS: int = 604800
    RUNNER_TIMEOUT_SECONDS: int = 10
    RUNNER_MAX_MEMORY_MB: int = 128

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()