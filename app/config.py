import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Enterprise AI Knowledge & Workflow Agent")
_DEFAULT_AI_MODE = os.getenv("AI_MODE", "local").strip().lower()
_DEFAULT_DATABASE_PATH = os.getenv(
    "LOCAL_DATABASE_PATH" if _DEFAULT_AI_MODE == "local" else "DATABASE_PATH",
    "data/knowledge-local.db" if _DEFAULT_AI_MODE == "local" else "data/knowledge.db",
)


@dataclass(frozen=True)
class Settings:
    """Validated application settings loaded from the environment."""

    app_name: str = APP_NAME
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    ai_mode: str = _DEFAULT_AI_MODE
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-4.1-mini")
    database_path: Path = Path(_DEFAULT_DATABASE_PATH)
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    top_k: int = int(os.getenv("TOP_K", "4"))
    min_relevance_score: float = float(os.getenv("MIN_RELEVANCE_SCORE", "0.15"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    )

    def __post_init__(self) -> None:
        normalized_mode = self.ai_mode.strip().lower()
        object.__setattr__(self, "ai_mode", normalized_mode)
        if self.ai_mode not in {"local", "openai"}:
            raise ValueError("AI_MODE must be either 'local' or 'openai'.")
        if self.chunk_size < 1:
            raise ValueError("CHUNK_SIZE must be positive")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be non-negative and smaller than CHUNK_SIZE")
        if not 1 <= self.top_k <= 20:
            raise ValueError("TOP_K must be between 1 and 20")
        if self.max_upload_bytes < 1:
            raise ValueError("MAX_UPLOAD_BYTES must be positive")
        if not 0 <= self.min_relevance_score <= 1:
            raise ValueError("MIN_RELEVANCE_SCORE must be between 0 and 1")
