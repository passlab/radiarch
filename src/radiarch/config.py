from functools import lru_cache
from typing import List, Optional, Any

from pydantic import AnyUrl, Field, SecretStr
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
    orthanc_use_mock: bool = Field(default=True, description="Use fake Orthanc adapter for development")

    # Database and artifact storage
    database_url: str = Field(default="", description="Leave empty to use InMemoryStore; set to sqlite:///./radiarch.db or postgresql+psycopg://... for persistence")
    artifact_dir: str = Field(default="./data/artifacts")
    upload_dir: str = Field(
        default="",
        description=(
            "Where uploaded DICOM ZIPs get extracted to. "
            "Empty (the default) resolves to {artifact_dir}/uploads at runtime."
        ),
    )

    # Session TTL
    session_ttl: int = Field(default=3600, description="Session expiration in seconds")

    # DICOMweb STOW-RS notification (vendor-neutral; empty = disabled)
    dicomweb_url: str = Field(default="", description="DICOMweb STOW-RS URL for artifact push; empty = disabled")
    dicomweb_username: Optional[str] = Field(default=None)
    dicomweb_password: Optional[str] = Field(default=None)
    # OAuth2 client credentials for a DICOMweb endpoint that wants a bearer token (a research write gateway);
    # used when the token URL and client id are set and no username is given. The secret is never logged.
    dicomweb_token_url: str = Field(default="", description="OAuth2 token endpoint (client_credentials grant); empty = no bearer token")
    dicomweb_client_id: str = Field(default="", description="OAuth2 client id for the DICOMweb push")
    dicomweb_client_secret: Optional[SecretStr] = Field(default=None, description="OAuth2 client secret for the DICOMweb push")
    dicomweb_token_scope: str = Field(default="", description="OAuth2 scope to request; empty = the client's default")
    # A DICOMweb viewer (OHIF) that reads from the push destination: a pushed export carries a link that opens its study
    viewer_url: str = Field(default="", description="OHIF base URL, e.g. http://localhost:3000; empty = no viewer link")

    # Job queue
    broker_url: str = Field(default="redis://localhost:6379/0")
    result_backend: str = Field(default="redis://localhost:6379/1")

    # Data and machine models
    data_root: str = Field(default="", description="Directory of DICOM (CT + RTSTRUCT) the geometry service reads when no upload or PACS study is given; empty = the bundled SimpleFantom under tests/data if present")
    beam_library_dir: str = Field(default="/data/radiarch/beam-models", description="Custom machine models: {beam_library_dir}/{id}/BDL.txt and Scanner/")

    cors_origins: List[str] = Field(default_factory=lambda: ["*"])

    # CCC photon engine: the WiscPlan binary and its kernels, run as a subprocess
    ccc_engine_dir: str = Field(
        default="",
        description=(
            "Directory holding CCC_DoseEngine/CCC_DoseEngine and Kernels_differentFluence. "
            "Empty = the copy vendored with OpenTPS core."
        ),
    )
    ccc_n_jobs: int = Field(default=4, ge=1, description="Parallel CCC processes per dose/Dij build.")
    ccc_scatter: str = Field(default="shipped", description="CCC scatter setting: 'shipped' (truncated at ~2 cm, fast) or 'full' (0.01 % cutoff, 10 cm mask; ~45x slower). Per-run params override.")
    ccc_calibration_spacing_mm: float = Field(
        default=2.5, gt=0,
        description="Grid spacing of the water phantom used to calibrate the CCC output (reference field).",
    )

    # Native photon pencil-beam engine (roadmap R8): kernels in engines/pb, NumPy or CuPy
    pb_device: str = Field(default="cpu", description="Pencil-beam engine device: 'cpu', 'gpu' (CuPy, fails when absent) or 'auto'. Per-run params override.")
    pb_n_jobs: int = Field(default=4, ge=1, description="Threads for the pencil-beam engine's influence matrix on the CPU.")
    pb_components: int = Field(default=0, ge=0, description="Kernel components of the pencil-beam engine; 0 = the engine's default.")
    pb_cutoff_mm: float = Field(default=0.0, ge=0.0, description="Lateral cutoff of the pencil-beam influence matrix (mm); 0 = the engine's default.")

    # MCsquare proton engine (roadmap R14): the binaries, launcher, Materials, BDL and
    # Scanners directory, run as a subprocess through radiarch's own driver.
    mcsquare_dir: str = Field(
        default="",
        description="Directory with the MCsquare launcher, binaries, Materials/, BDL/ and Scanners/. Empty = the copy vendored with OpenTPS core.",
    )
    mcsquare_n_threads: int = Field(default=0, ge=0, description="Engine threads per run; 0 = all cores.")
    mcsquare_seed: int = Field(default=0, ge=0, description="RNG seed; 0 = from the clock (deterministic runs need a seed and one thread).")
    mcsquare_scanner: str = Field(default="UCL_Toshiba", description="Scanner calibration under Scanners/ (or an absolute directory).")
    mcsquare_bdl: str = Field(default="BDL_default_DN_RangeShifter.txt", description="Beam data library under BDL/ (or an absolute path).")
    mcsquare_keep_workdir: bool = Field(default=False, description="Keep each run's input and output files under {artifact_dir}/mcsquare for inspection.")

    # -------------------------------------------------------------------
    # D7.1 — Celery resource limits (per-task overrides for dose work)
    # -------------------------------------------------------------------
    celery_default_time_limit_s: int = Field(
        default=1800,
        description="Hard time limit for non-dose Celery tasks (seconds).",
    )
    celery_default_soft_time_limit_s: int = Field(
        default=1500,
        description="Soft time limit for non-dose Celery tasks (seconds).",
    )
    dose_soft_time_limit_s: int = Field(
        default=3600,
        description=(
            "Soft time limit (SoftTimeLimitExceeded) for dose compute "
            "tasks. Influence builds get 2x this. Bump for clinical-grid "
            "MCsquare runs."
        ),
    )
    dose_hard_time_limit_s: int = Field(
        default=4200,
        description=(
            "Hard SIGKILL time limit for dose compute tasks. Must be "
            "greater than dose_soft_time_limit_s by enough headroom "
            "for graceful cleanup."
        ),
    )
    dose_rate_limit: str = Field(
        default="6/m",
        description=(
            "Celery rate-limit string applied to dose tasks. Prevents "
            "a flood of MCsquare jobs from spiking CPU/IO."
        ),
    )
    celery_worker_max_memory_kb: int = Field(
        default=4_000_000,  # 4 GB
        description=(
            "Worker recycles after exceeding this RSS (KB). Protects "
            "against MCsquare/numpy memory leaks. Set to 0 to disable."
        ),
    )
    celery_worker_max_tasks: int = Field(
        default=50,
        description=(
            "Worker recycles after this many tasks. Belt-and-suspenders "
            "against slow memory growth. Set to 0 to disable."
        ),
    )

    # -------------------------------------------------------------------
    # O20 — Optimization Service (Service 4) resource limits + cleanup
    # -------------------------------------------------------------------
    optimization_soft_time_limit_s: int = Field(
        default=14400,  # 4h — optimization is the heaviest stage (many Dij·w)
        description="Soft time limit for optimization run tasks (seconds).",
    )
    optimization_hard_time_limit_s: int = Field(
        default=15000,
        description="Hard SIGKILL time limit for optimization run tasks.",
    )
    optimize_rate_limit: str = Field(
        default="2/m",
        description="Celery rate-limit string applied to optimization tasks.",
    )
    optimization_store_max_gb: float = Field(
        default=30.0,
        description="Soft cap on total optimization cache size (LRU eviction).",
    )
    optimization_checkpoint_keep: int = Field(
        default=5,
        description="Keep only the latest N checkpoints per optimization id.",
    )

    # -------------------------------------------------------------------
    # Service 5 — BAO (Beam Angle Optimization) resource limits + cleanup
    # -------------------------------------------------------------------
    bao_soft_time_limit_s: int = Field(
        default=28800,  # 8h — scores many angle sets, each a fluence opt
        description="Soft time limit for BAO run tasks (seconds).",
    )
    bao_hard_time_limit_s: int = Field(
        default=30000,
        description="Hard SIGKILL time limit for BAO run tasks.",
    )
    bao_rate_limit: str = Field(
        default="1/m",
        description="Celery rate-limit string applied to BAO tasks.",
    )
    bao_store_max_gb: float = Field(
        default=5.0,
        description="Soft cap on total BAO cache size (metadata only; small).",
    )

    # -------------------------------------------------------------------
    # Service 6 — Evaluation resource limits + cleanup
    # -------------------------------------------------------------------
    evaluation_soft_time_limit_s: int = Field(
        default=1800,
        description="Soft time limit for evaluation run tasks (gamma dominates).",
    )
    evaluation_hard_time_limit_s: int = Field(
        default=2400,
        description="Hard SIGKILL time limit for evaluation run tasks.",
    )
    evaluate_rate_limit: str = Field(
        default="30/m",
        description="Celery rate-limit string applied to evaluation tasks.",
    )
    evaluation_store_max_gb: float = Field(
        default=5.0,
        description="Soft cap on total evaluation cache size (metadata only).",
    )

    # -------------------------------------------------------------------
    # D7.2 — Disk-space + cleanup policy
    # -------------------------------------------------------------------
    cleanup_interval_s: int = Field(
        default=3600,
        description="Seconds between disk-cleanup Celery Beat ticks.",
    )
    dose_store_max_gb: float = Field(
        default=50.0,
        description=(
            "Soft cap on total dose cache size. When exceeded the "
            "cleanup task evicts least-recently-accessed entries."
        ),
    )
    influence_store_max_gb: float = Field(
        default=100.0,
        description="Same as dose_store_max_gb but for the Dij cache.",
    )
    dose_min_age_hours: int = Field(
        default=24,
        description=(
            "Don't evict dose/influence entries younger than this — "
            "protects an active optimization loop from losing its Dij."
        ),
    )

    # -------------------------------------------------------------------
    # D7.3 — Structured audit logging
    # -------------------------------------------------------------------
    audit_log_path: str = Field(
        default="",
        description=(
            "If set, append JSONL audit events here in addition to "
            "stderr. Empty disables file sink. One line per event."
        ),
    )

    # -------------------------------------------------------------------
    # D8.2 — Static API key (set empty to disable auth)
    # -------------------------------------------------------------------
    api_key: str = Field(
        default="",
        description=(
            "Static API key required in X-API-Key header for protected "
            "routes (dose + influence). Empty disables auth (dev only)."
        ),
    )
    api_key_header: str = Field(
        default="X-API-Key",
        description="Header name carrying the API key.",
    )

    # Test-only dose engines (the analytic engine: right shape, wrong physics)
    allow_test_engines: Optional[bool] = Field(
        default=None,
        description=(
            "Permit test-only dose engines. Unset = allowed only when "
            "environment is 'dev'; never enable in a deployment."
        ),
    )


@lru_cache
def get_settings() -> Settings:
    import sys
    import os
    import site

    settings = Settings()

    if settings.allow_test_engines is None:
        settings.allow_test_engines = settings.environment == "dev"

    # Auto-detect the data root from the bundled test data if not set
    if not settings.data_root:
        # Walk up from config.py → radiarch/ → src/ → repo root
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
        test_data = os.path.join(repo_root, "tests", "data", "SimpleFantomWithStruct")
        if os.path.isdir(test_data):
            settings.data_root = test_data

    return settings
