from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    corpus_dir: str = "./data/corpus"
    manifest_path: str = "./data/manifest.json"
    db_path: str = "./data/veltrix.db"
    app_today: str = ""

    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "auto"  # auto | cpu | cuda
    rerank_enabled: str = "auto"    # auto (GPU only) | true | false
    rerank_model: str = "BAAI/bge-reranker-base"
    corpus_token_budget: int = 3000

    def today(self) -> date:
        return date.fromisoformat(self.app_today) if self.app_today else date.today()

    def provider_key(self) -> str:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "gemini": self.google_api_key,
        }.get(self.llm_provider, "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
