"""Runtime settings. Environment variables override defaults. A missing key stays offline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines into the environment without overriding real variables."""
    file = Path(path)
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_provider: str = "local"
    embedding_model: str = "text-embedding-3-small"
    database_url: str = "sqlite:///data/hinga.db"
    session_secret: str = "dev-only-change-me"
    fernet_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8741

    @property
    def llm_mode(self) -> str:
        """`llm` only when a compatible endpoint is both selected and keyed."""
        provider = self.llm_provider.strip().lower()
        if provider in {"openai", "compatible", "live"} and self.llm_api_key.strip():
            return "llm"
        return "mock"

    @property
    def embedding_mode(self) -> str:
        if self.embedding_provider.strip().lower() == "openai" and self.llm_api_key.strip():
            return "openai"
        return "local"

    @property
    def database_kind(self) -> str:
        if self.database_url.startswith("sqlite"):
            return "sqlite"
        return "postgres"

    @property
    def llm_label(self) -> str:
        if self.llm_mode == "llm":
            return f"Live model · {self.llm_model}"
        return "Offline reflection"


def load_settings() -> Settings:
    load_dotenv()
    port = int(os.environ.get("HINGA_PORT") or os.environ.get("PORT") or 8741)
    return Settings(
        llm_provider=os.environ.get("LLM_PROVIDER", "mock"),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        embedding_provider=os.environ.get("EMBEDDING_PROVIDER", "local"),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///data/hinga.db"),
        session_secret=os.environ.get("SESSION_SECRET", "dev-only-change-me"),
        fernet_key=os.environ.get("HINGA_FERNET_KEY", ""),
        host=os.environ.get("HINGA_HOST", "0.0.0.0"),
        port=port,
    )
