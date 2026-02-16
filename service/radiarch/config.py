from functools import lru_cache
from typing import List, Optional

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Radiarch global configuration."""

    model_config = SettingsConfigDict(env_prefix="RADIARCH_", env_file=".env", env_file_encoding="utf-8")

    project_name: str = Field(default="Radiarch TPS Service")
    api_prefix: str = Field(default="/api/v1")
    environment: str = Field(default="dev")

    # Orthanc / PACS configuration
    orthanc_base_url: AnyUrl | str = Field(default="http://localhost:8042")
    orthanc_username: Optional[str] = Field(default=None)
    orthanc_password: Optional[str] = Field(default=None)

    # Database and artifact storage
    database_url: str = Field(default="sqlite+aiosqlite:///./radiarch.db")
    artifact_dir: str = Field(default="./data/artifacts")

    # Job queue
    broker_url: str = Field(default="redis://localhost:6379/0")
    result_backend: str = Field(default="redis://localhost:6379/1")

    # OpenTPS configuration
    opentps_data_root: str = Field(default="./opentps-data")
    opentps_beam_library: str = Field(default="./opentps-data/beam-models")

    cors_origins: List[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
