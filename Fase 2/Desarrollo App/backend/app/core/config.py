from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "dev"
    API_BASE_URL: str = "http://localhost:8000"
    PUBLIC_CHAT_BASE_URL: str = "https://soporte.allox.ai"
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    DATABASE_URL: str = "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_PRIVATE_KEY_PEM: str = ""
    JWT_PUBLIC_KEY_PEM: str = ""
    ACCESS_TOKEN_MINUTES: int = 30
    REFRESH_TOKEN_DAYS: int = 7
    SESSION_TOKEN_HOURS: int = 24

    SECRETS_BACKEND: str = "env"          # env | keyvault
    AZURE_KEY_VAULT_URL: str = ""

    STORAGE_BACKEND: str = "local"        # local | azure_blob
    LOCAL_STORAGE_DIR: str = "./var/storage"
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = "documents"

    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_DEFAULT_MODEL: str = "deepseek-chat"

    EMBEDDINGS_BACKEND: str = "hash"      # azure_openai | hash
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    META_GRAPH_BASE_URL: str = "https://graph.facebook.com/v20.0"
    WHATSAPP_VERIFY_TOKEN: str = "verify-token"
    WHATSAPP_APP_SECRET: str = ""

    WORKERS_INLINE: bool = True

    MAX_DOCUMENT_MB: int = 25
    PUBLIC_MSG_PER_MINUTE: int = 20
    DEFAULT_TOKEN_LIMIT_MONTH: int = 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
