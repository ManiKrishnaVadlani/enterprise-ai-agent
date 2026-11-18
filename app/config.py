import os
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Enterprise AI Knowledge & Workflow Agent")
_DEFAULT_AI_MODE = os.getenv("AI_MODE", "local").strip().lower()
_DEFAULT_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
_OLLAMA_THINK_ENV = os.getenv("OLLAMA_THINK", "false").strip().lower()
if _OLLAMA_THINK_ENV not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
    raise ValueError("OLLAMA_THINK must be a boolean value.")
_DEFAULT_OLLAMA_THINK = _OLLAMA_THINK_ENV in {"true", "1", "yes", "on"}
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
    llm_provider: str = _DEFAULT_LLM_PROVIDER
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3.5:2b-q4_K_M")
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
    ollama_temperature: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
    ollama_think: bool = _DEFAULT_OLLAMA_THINK
    ollama_num_predict: int = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))
    ollama_context_length: int = int(os.getenv("OLLAMA_CONTEXT_LENGTH", "4096"))
    ollama_max_prompt_chars: int = int(os.getenv("OLLAMA_MAX_PROMPT_CHARS", "12000"))
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-4.1-mini")
    database_path: Path = Path(_DEFAULT_DATABASE_PATH)
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    top_k: int = int(os.getenv("TOP_K", "4"))
    min_relevance_score: float = float(os.getenv("MIN_RELEVANCE_SCORE", "0.15"))
    local_min_relevance_score: float | None = (
        float(os.environ["LOCAL_MIN_RELEVANCE_SCORE"])
        if "LOCAL_MIN_RELEVANCE_SCORE" in os.environ
        else None
    )
    openai_min_relevance_score: float | None = (
        float(os.environ["OPENAI_MIN_RELEVANCE_SCORE"])
        if "OPENAI_MIN_RELEVANCE_SCORE" in os.environ
        else None
    )
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    max_concurrent_uploads: int = int(os.getenv("MAX_CONCURRENT_UPLOADS", "2"))
    upload_wait_timeout_seconds: float = float(
        os.getenv("UPLOAD_WAIT_TIMEOUT_SECONDS", "5")
    )
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "200"))
    max_extracted_text_chars: int = int(
        os.getenv("MAX_EXTRACTED_TEXT_CHARS", "2000000")
    )
    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "120"))
    rate_limit_window_seconds: float = float(
        os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    )
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
        llm_provider = self.llm_provider.strip().lower()
        if not llm_provider:
            llm_provider = "openai" if normalized_mode == "openai" else "extractive"
        object.__setattr__(self, "llm_provider", llm_provider)
        normalized_log_level = self.log_level.strip().upper()
        object.__setattr__(self, "log_level", normalized_log_level)
        if self.ai_mode not in {"local", "openai"}:
            raise ValueError("AI_MODE must be either 'local' or 'openai'.")
        if llm_provider not in {"extractive", "ollama", "openai"}:
            raise ValueError("LLM_PROVIDER must be extractive, ollama, or openai.")
        if not self.ollama_model.strip() or any(c in self.ollama_model for c in "\r\n"):
            raise ValueError("OLLAMA_MODEL must be a non-empty model name.")
        if (
            not math.isfinite(self.ollama_timeout_seconds)
            or self.ollama_timeout_seconds <= 0
        ):
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be positive and finite.")
        if (
            not math.isfinite(self.ollama_temperature)
            or not 0 <= self.ollama_temperature <= 2
        ):
            raise ValueError("OLLAMA_TEMPERATURE must be between 0 and 2.")
        if not 1 <= self.ollama_num_predict <= 4096:
            raise ValueError("OLLAMA_NUM_PREDICT must be between 1 and 4096.")
        if not 512 <= self.ollama_context_length <= 32768:
            raise ValueError("OLLAMA_CONTEXT_LENGTH must be between 512 and 32768.")
        if not 1 <= self.ollama_max_prompt_chars <= 100000:
            raise ValueError("OLLAMA_MAX_PROMPT_CHARS must be between 1 and 100000.")
        if not isinstance(self.ollama_think, bool):
            raise ValueError("OLLAMA_THINK must be a boolean value.")
        parsed_runtime = urlsplit(self.ollama_base_url)
        try:
            runtime_port = parsed_runtime.port
        except ValueError as error:
            raise ValueError("OLLAMA_BASE_URL must be a valid local HTTP URL.") from error
        if (
            parsed_runtime.scheme != "http"
            or (
                parsed_runtime.hostname
                not in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
            )
            or parsed_runtime.username is not None
            or parsed_runtime.password is not None
            or parsed_runtime.query
            or parsed_runtime.fragment
            or parsed_runtime.path not in {"", "/"}
            or (runtime_port is not None and not 1 <= runtime_port <= 65535)
        ):
            raise ValueError(
                "OLLAMA_BASE_URL must use HTTP and a loopback or Docker host name."
            )
        if normalized_log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
        if self.chunk_size < 1:
            raise ValueError("CHUNK_SIZE must be positive")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be non-negative and smaller than CHUNK_SIZE")
        if not 1 <= self.top_k <= 20:
            raise ValueError("TOP_K must be between 1 and 20")
        if self.max_upload_bytes < 1:
            raise ValueError("MAX_UPLOAD_BYTES must be positive")
        if self.max_concurrent_uploads < 1:
            raise ValueError("MAX_CONCURRENT_UPLOADS must be positive")
        if (
            not math.isfinite(self.upload_wait_timeout_seconds)
            or self.upload_wait_timeout_seconds <= 0
        ):
            raise ValueError("UPLOAD_WAIT_TIMEOUT_SECONDS must be positive and finite")
        if self.max_pdf_pages < 1:
            raise ValueError("MAX_PDF_PAGES must be positive")
        if self.max_extracted_text_chars < 1:
            raise ValueError("MAX_EXTRACTED_TEXT_CHARS must be positive")
        if self.rate_limit_requests < 1:
            raise ValueError("RATE_LIMIT_REQUESTS must be positive")
        if (
            not math.isfinite(self.rate_limit_window_seconds)
            or self.rate_limit_window_seconds <= 0
        ):
            raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be positive and finite")
        if not math.isfinite(self.min_relevance_score) or not 0 <= self.min_relevance_score <= 1:
            raise ValueError("MIN_RELEVANCE_SCORE must be between 0 and 1")
        for name, threshold in (
            ("LOCAL_MIN_RELEVANCE_SCORE", self.local_min_relevance_score),
            ("OPENAI_MIN_RELEVANCE_SCORE", self.openai_min_relevance_score),
        ):
            if threshold is not None and (
                not math.isfinite(threshold) or not 0 <= threshold <= 1
            ):
                raise ValueError(f"{name} must be between 0 and 1")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must contain explicit HTTP(S) origins without paths."
                )

    def relevance_threshold_for(self, ai_mode: str) -> float:
        """Return a provider-specific override or the legacy shared setting."""
        if ai_mode == "local" and self.local_min_relevance_score is not None:
            return self.local_min_relevance_score
        if ai_mode == "openai" and self.openai_min_relevance_score is not None:
            return self.openai_min_relevance_score
        return self.min_relevance_score
