"""Configuration API routes."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from .models import (
    ModelsListResponse,
    ModelInfo,
    PromptsListResponse,
    PromptTypeInfo,
    PromptValidationRequest,
    PromptValidationResponse,
    SettingsResponse,
)
from .services import PromptManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["configuration"])


# Dependency injection
_prompt_manager: Optional[PromptManager] = None


def set_prompt_manager(prompt_manager: PromptManager):
    """Set prompt manager instance (called from main.py)."""
    global _prompt_manager
    _prompt_manager = prompt_manager


def get_prompt_manager() -> PromptManager:
    """Get prompt manager instance."""
    if _prompt_manager is None:
        raise HTTPException(status_code=500, detail="PromptManager not initialized")
    return _prompt_manager


@router.get("/models", response_model=ModelsListResponse)
async def list_models():
    """
    List available models.

    Returns:
        ModelsListResponse with model information
    """
    from config.settings import get_settings
    settings = get_settings()
    configs = settings.load_model_configs()

    models = []
    for model_id, config in configs.get('models', {}).items():
        model_info = ModelInfo(
            model_id=model_id,
            name=config.get('name', model_id),
            description=config.get('description', ''),
            capabilities=config.get('capabilities', ['ocr']),
            estimated_memory_gb=config.get('memory_gb', 0.0),
            default=(model_id == settings.default_model),
        )
        models.append(model_info)

    return ModelsListResponse(models=models)


@router.get("/prompts", response_model=PromptsListResponse)
async def list_prompts(
    prompt_manager: PromptManager = Depends(get_prompt_manager)
):
    """
    List available prompt types and default templates.

    Returns:
        PromptsListResponse with prompt type information
    """
    prompt_types_data = prompt_manager.list_prompt_types()

    prompt_types = [
        PromptTypeInfo(
            type=pt['type'],
            description=pt['description'],
            default_template=pt['default_template'],
            variables=pt['variables']
        )
        for pt in prompt_types_data
    ]

    return PromptsListResponse(prompt_types=prompt_types)


@router.post("/prompts/validate", response_model=PromptValidationResponse)
async def validate_prompt(
    request: PromptValidationRequest,
    prompt_manager: PromptManager = Depends(get_prompt_manager)
):
    """
    Validate a custom prompt.

    Args:
        request: Prompt validation request

    Returns:
        PromptValidationResponse with validation results
    """
    validation = prompt_manager.validate_prompt(
        prompt_type=request.prompt_type,
        template=request.template,
        model=request.model
    )

    return PromptValidationResponse(
        valid=validation.valid,
        warnings=validation.warnings,
        required_variables=validation.required_variables,
        found_variables=validation.found_variables,
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """
    Get current system settings.

    Returns:
        SettingsResponse with system configuration
    """
    from config.settings import get_settings
    settings = get_settings()

    return SettingsResponse(
        max_upload_size_mb=settings.max_upload_size_mb,
        default_output_format=settings.default_output_format,
        default_dpi=300,  # Hardcoded for now
        default_model=settings.default_model,
        max_batch_size=settings.max_batch_size,
        enable_staged_pipeline=True,  # Hardcoded for now
        temp_file_expiry_hours=settings.temp_file_expiry_hours,
    )
