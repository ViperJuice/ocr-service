"""Application settings using Pydantic."""
import os
import json
from pathlib import Path
from typing import List, Literal, Union
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Model Configuration
    default_model: Literal["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b", "deepseek-ocr"] = Field(
        default="deepseek-ocr",
        description="Default model to use for OCR"
    )

    # Container Configuration
    deepseek_container_url: str = Field(
        default="http://localhost:8001",
        description="DeepSeek-OCR container base URL"
    )
    qwen_container_url: str = Field(
        default="http://localhost:8002",
        description="Qwen3-VL container base URL"
    )
    container_timeout: float = Field(
        default=300.0,
        description="Container inference timeout in seconds"
    )
    enable_container_orchestration: bool = Field(
        default=True,
        description="Enable container lifecycle orchestration (start/stop between jobs). "
                    "Disable for multi-GPU batch processing to keep containers running."
    )
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    api_workers: int = Field(default=1, description="Number of API workers")
    max_upload_size_mb: int = Field(default=50, description="Max upload size in MB")
    enable_cors: bool = Field(default=True, description="Enable CORS")
    cors_origins: Union[List[str], str] = Field(
        default=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://172.22.180.9:3000"],
        description="Allowed CORS origins"
    )

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from JSON string if needed."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If not valid JSON, split by comma
                return [origin.strip() for origin in v.split(',')]
        return v
    
    # Processing Configuration
    max_batch_size: int = Field(default=10, description="Maximum batch size")
    max_image_size: int = Field(default=4096, description="Maximum image dimension")
    default_output_format: Literal["markdown", "text", "json", "html"] = Field(
        default="markdown",
        description="Default output format"
    )
    enable_caching: bool = Field(default=False, description="Enable result caching")
    cache_backend: Literal["file", "redis"] = Field(
        default="file",
        description="Cache backend"
    )
    cache_ttl: int = Field(default=3600, description="Cache TTL in seconds")
    enable_merge_streaming: bool = Field(
        default=True,
        description="Enable streaming merge text chunks (Phase 3.6)"
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: Literal["json", "text"] = Field(default="json", description="Log format")
    log_file: str = Field(default="logs/ocr-service.log", description="Log file path")

    # Supabase Configuration
    supabase_url: str = Field(
        default="http://localhost:54321",
        description="Supabase API URL"
    )
    supabase_anon_key: str = Field(
        default="",
        description="Supabase anonymous key (client-side)"
    )
    supabase_service_role_key: str = Field(
        default="",
        description="Supabase service role key (backend - bypasses RLS)"
    )
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:54322/postgres",
        description="Direct PostgreSQL connection URL"
    )

    # Supabase Storage Buckets
    supabase_storage_bucket_uploads: str = Field(
        default="ocr-uploads",
        description="Storage bucket for uploaded files"
    )
    supabase_storage_bucket_results: str = Field(
        default="ocr-results",
        description="Storage bucket for OCR results"
    )

    # Development Test User
    dev_user_id: str = Field(
        default="a0000000-0000-0000-0000-000000000001",
        description="Development test user ID"
    )
    dev_api_key: str = Field(
        default="dev_test_key_12345",
        description="Development test API key"
    )

    # API Storage Configuration
    api_temp_directory: str = Field(
        default="data/temp",
        description="Temporary directory for uploaded files"
    )
    api_processing_directory: str = Field(
        default="data/processing",
        description="Directory for active processing workspace"
    )
    api_output_directory: str = Field(
        default="data/output",
        description="Directory for completed results"
    )
    temp_file_expiry_hours: int = Field(
        default=6,
        description="Hours until uploaded files expire"
    )
    max_job_history: int = Field(
        default=100,
        description="Maximum number of jobs to keep in history"
    )
    job_cleanup_interval_hours: int = Field(
        default=1,
        description="Interval for cleanup tasks in hours"
    )

    @property
    def project_root(self) -> Path:
        """Get project root directory."""
        return Path(__file__).parent.parent
    
    @property
    def config_dir(self) -> Path:
        """Get config directory."""
        return self.project_root / "config"
    
    @property
    def data_dir(self) -> Path:
        """Get data directory."""
        return self.project_root / "data"
    
    @property
    def model_configs_path(self) -> Path:
        """Get model configs YAML path."""
        return self.config_dir / "model_configs.yaml"
    
    def load_model_configs(self) -> dict:
        """Load model configurations from YAML."""
        with open(self.model_configs_path, 'r') as f:
            return yaml.safe_load(f)
    
    def setup_environment(self) -> None:
        """Set up environment variables."""
        # Container mode only - minimal environment setup
        pass


def get_settings() -> Settings:
    """Get settings instance."""
    settings = Settings()
    settings.setup_environment()
    return settings

