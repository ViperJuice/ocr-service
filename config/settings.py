"""Application settings using Pydantic."""
import os
from pathlib import Path
from typing import List, Literal
from functools import lru_cache

from pydantic import Field
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
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    api_workers: int = Field(default=1, description="Number of API workers")
    max_upload_size_mb: int = Field(default=50, description="Max upload size in MB")
    enable_cors: bool = Field(default=True, description="Enable CORS")
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"],
        description="Allowed CORS origins"
    )
    
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
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: Literal["json", "text"] = Field(default="json", description="Log format")
    log_file: str = Field(default="logs/ocr-service.log", description="Log file path")

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


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.setup_environment()
    return settings

