from functools import lru_cache
from typing import List, Optional, Any

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Radiarch global configuration."""

    model_config = SettingsConfigDict(env_prefix="RADIARCH_", env_file=".env", env_file_encoding="utf-8")

    project_name: str = Field(default="Radiarch TPS Service")
    api_prefix: str = Field(default="/api/v1")
    environment: str = Field(default="dev")

    # Force synthetic planner (skips OpenTPS/MCsquare)
    force_synthetic: bool = Field(default=False, description="Use synthetic planner instead of OpenTPS")

    # Orthanc / PACS configuration
    orthanc_base_url: AnyUrl | str = Field(default="http://localhost:8042")
    orthanc_username: Optional[str] = Field(default=None)
    orthanc_password: Optional[str] = Field(default=None)
    orthanc_use_mock: bool = Field(default=True, description="Use fake Orthanc adapter for development")

    # Database and artifact storage
    database_url: str = Field(default="", description="Leave empty to use InMemoryStore; set to sqlite:///./radiarch.db or postgresql+psycopg://... for persistence")
    artifact_dir: str = Field(default="./data/artifacts")

    # Session TTL
    session_ttl: int = Field(default=3600, description="Session expiration in seconds")

    # DICOMweb STOW-RS notification (vendor-neutral; empty = disabled)
    dicomweb_url: str = Field(default="", description="DICOMweb STOW-RS URL for artifact push; empty = disabled")
    dicomweb_username: Optional[str] = Field(default=None)
    dicomweb_password: Optional[str] = Field(default=None)

    # Job queue
    broker_url: str = Field(default="redis://localhost:6379/0")
    result_backend: str = Field(default="redis://localhost:6379/1")

    # OpenTPS configuration (only needed when force_synthetic=false)
    opentps_data_root: str = Field(default="/data/opentps")
    opentps_beam_library: str = Field(default="/data/opentps/beam-models")
    opentps_venv: str = Field(default="", description="Path to OpenTPS venv site-packages; empty = skip")

    cors_origins: List[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    import sys
    import os
    import site

    settings = Settings()

    # Add OpenTPS venv site-packages to sys.path if configured
    venv_path = settings.opentps_venv
    if venv_path and os.path.exists(venv_path):
        site.addsitedir(venv_path)

    return settings
