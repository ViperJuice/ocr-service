"""Batch processing data models."""
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class BatchJobStatus(Enum):
    """Batch job status enum."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchJob:
    """Batch job containing multiple document jobs."""
    batch_job_id: str
    directory_id: str
    file_ids: List[str]
    document_jobs: Dict[str, Any]  # job_id -> Job (Any to avoid circular import)
    total_documents: int
    documents_completed: int
    overall_progress_pct: float
    status: BatchJobStatus
    created_at: datetime
    model: str
    prompt_type: str
    custom_prompts: Optional[Dict[str, str]]
    processing_options: Dict[str, Any]
    output_format: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    cancel_requested: bool = False


@dataclass
class BatchProgress:
    """Real-time batch progress information."""
    batch_job_id: str
    overall_progress_pct: float
    documents_completed: int
    total_documents: int
    current_document_id: Optional[str] = None
    current_document_filename: Optional[str] = None
    current_document_progress_pct: Optional[float] = None
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
    current_stage: Optional[str] = None
