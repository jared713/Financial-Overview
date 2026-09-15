from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Comma-separated list of allowed browser origins. Plain string (not JSON) so
    # it survives Railway's env var UI without escaping headaches.
    cors_origins: str = "http://localhost:3000"

    # Companies House
    # Register a key at https://developer.company-information.service.gov.uk/
    companies_house_api_key: str | None = None

    # Saved analyses. Point this at a mounted Railway volume to keep results
    # across redeploys; without one the app still saves, but to ephemeral disk.
    data_dir: str = "/data"

    # Claude review of filing PDFs
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    anthropic_max_tokens: int = 8000

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
