"""Pydantic request models for API."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Literal


class ProcessingOptions(BaseModel):
    """Processing configuration options."""
    dpi: int = Field(default=300, ge=72, le=600)
    method: Literal["auto", "extract", "ocr", "hybrid"] = "auto"
    start_page: Optional[int] = Field(default=None, ge=1)
    end_page: Optional[int] = Field(default=None, ge=1)
    staged_pipeline: bool = True
    prefer_quality: bool = True

    @field_validator('end_page')
    @classmethod
    def end_page_must_be_greater_than_start(cls, v, info):
        if v and info.data.get('start_page') and v < info.data['start_page']:
            raise ValueError('end_page must be >= start_page')
        return v


class JobSubmitRequest(BaseModel):
    """Request to submit a processing job."""
    file_id: str
    model: Optional[str] = None
    prompt_type: Optional[str] = "markdown"
    custom_prompts: Optional[Dict[str, str]] = None
    processing_options: Optional[ProcessingOptions] = Field(default_factory=ProcessingOptions)
    output_format: Literal["markdown", "text", "json"] = "markdown"


class PromptValidationRequest(BaseModel):
    """Request to validate a custom prompt."""
    prompt_type: str
    template: str
    model: str


class BatchProcessRequest(BaseModel):
    """Request to process a batch of documents."""
    directory_id: str = Field(..., description="Directory ID containing PDFs")
    model: str = Field(default="deepseek-ai/deepseek-vl2", description="Model to use")
    prompt_type: str = Field(default="default", description="Prompt type")
    custom_prompts: Optional[Dict[str, str]] = Field(None, description="Custom prompts")
    processing_options: Optional[ProcessingOptions] = Field(
        default_factory=ProcessingOptions,
        description="Processing options (dpi, prefer_quality, etc.)"
    )
    output_format: Literal["markdown", "text", "json"] = Field(default="markdown", description="Output format")
