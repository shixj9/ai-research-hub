import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def _parse_origins(value: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in value.split(",") if origin.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    app_env: str
    api_v1_prefix: str
    cors_origins: tuple[str, ...]
    database_url: str
    storage_root: Path
    max_pdf_size_bytes: int


@lru_cache
def get_settings() -> Settings:
    storage_root = Path(os.getenv("STORAGE_ROOT", "storage/dev"))
    if not storage_root.is_absolute():
        storage_root = PROJECT_ROOT / storage_root

    return Settings(
        app_name=os.getenv("APP_NAME", "AI Research Hub API"),
        app_version="0.1.0",
        app_env=os.getenv("APP_ENV", "development"),
        api_v1_prefix=os.getenv("API_V1_PREFIX", "/api/v1"),
        cors_origins=_parse_origins(
            os.getenv(
                "BACKEND_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,"
                "https://localhost:5173,https://127.0.0.1:5173",
            )
        ),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://ai_research_hub:ai_research_hub_dev@127.0.0.1:5432/"
            "ai_research_hub",
        ),
        storage_root=storage_root.resolve(),
        max_pdf_size_bytes=max(1, int(os.getenv("MAX_PDF_SIZE_MB", "100"))) * 1024 * 1024,
    )
