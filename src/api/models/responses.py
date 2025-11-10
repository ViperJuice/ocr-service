"""Pydantic response models for API."""
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime


class FileUploadResponse(BaseModel):
    """Response for file upload."""
    file_id: str
    filename: str
    size_bytes: int
    mime_type: str
    uploaded_at: datetime
    expires_at: datetime


class JobSubmitResponse(BaseModel):
    """Response for job submission."""
    job_id: str
    status: Literal["queued"]
    created_at: datetime
    file_id: str
    estimated_pages: Optional[int] = None
    monitor_url: str


class JobStatusResponse(BaseModel):
    """Response for job status."""
    job_id: str
    status: Literal["queued", "processing", "completed", "failed", "cancelled"]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    file_id: str
    filename: str
    total_pages: Optional[int] = None
    pages_completed: int
    current_stage: Optional[str] = None
    progress_pct: float
    estimated_remaining_seconds: Optional[int] = None
    error: Optional[str] = None


class JobResultResponse(BaseModel):
    """Response for job result."""
    job_id: str
    status: Literal["completed"]
    result: Dict[str, Any]
    completed_at: datetime


class ModelInfo(BaseModel):
    """Model information."""
    model_id: str
    name: str
    description: str
    capabilities: List[str]
    estimated_memory_gb: float
    default: bool


class ModelsListResponse(BaseModel):
    """Response for models list."""
    models: List[ModelInfo]


class PromptTypeInfo(BaseModel):
    """Prompt type information."""
    type: str
    description: str
    default_template: str
    variables: List[str]


class PromptsListResponse(BaseModel):
    """Response for prompts list."""
    prompt_types: List[PromptTypeInfo]


class PromptValidationResponse(BaseModel):
    """Response for prompt validation."""
    valid: bool
    warnings: List[str]
    required_variables: List[str]
    found_variables: List[str]


class SettingsResponse(BaseModel):
    """Response for system settings."""
    max_upload_size_mb: int
    default_output_format: str
    default_dpi: int
    default_model: str
    max_batch_size: int
    enable_staged_pipeline: bool
    temp_file_expiry_hours: int


class FileMetadataResponse(BaseModel):
    """Response for file metadata."""
    file_id: str
    filename: str
    size_bytes: int
    mime_type: str
    uploaded_at: datetime
    expires_at: datetime
    page_count: Optional[int] = None


class FileDeleteResponse(BaseModel):
    """Response for file deletion."""
    file_id: str
    deleted: bool


class JobCancelResponse(BaseModel):
    """Response for job cancellation."""
    job_id: str
    status: Literal["cancelled"]
    message: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class DirectoryUploadResponse(BaseModel):
    """Response for directory upload."""
    directory_id: str
    name: str
    file_count: int
    total_size: int
    files: List[Dict[str, Any]]


class BatchJobResponse(BaseModel):
    """Response for batch job creation/status."""
    batch_job_id: str
    directory_id: str
    total_documents: int
    documents_completed: int
    overall_progress_pct: float
    status: Literal["queued", "processing", "completed", "failed", "cancelled"]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class BatchResultResponse(BaseModel):
    """Response containing all batch results."""
    batch_job_id: str
    total_documents: int
    documents_completed: int
    results: List[Dict[str, Any]]
    overall_processing_time_seconds: float
