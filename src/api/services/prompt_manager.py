"""Prompt override and validation service."""
import re
import logging
from typing import Dict, Optional, List
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class ValidationResult:
    """Result from prompt validation."""

    def __init__(
        self,
        valid: bool,
        warnings: List[str],
        required_variables: List[str],
        found_variables: List[str]
    ):
        self.valid = valid
        self.warnings = warnings
        self.required_variables = required_variables
        self.found_variables = found_variables


class PromptManager:
    """Manage prompt templates and custom overrides."""

    def __init__(self, model_configs_path: Path):
        """
        Initialize prompt manager.

        Args:
            model_configs_path: Path to model_configs.yaml
        """
        self.model_configs_path = model_configs_path
        self._configs = None
        logger.info(f"PromptManager initialized with config: {model_configs_path}")

    def _load_configs(self) -> dict:
        """Load model configurations from YAML."""
        if self._configs is None:
            with open(self.model_configs_path, 'r') as f:
                self._configs = yaml.safe_load(f)
        return self._configs

    def get_default_prompts(self, model: str) -> Dict[str, str]:
        """
        Load default prompts for a model from YAML.

        Args:
            model: Model name (e.g., "qwen3-vl-8b", "deepseek-ocr")

        Returns:
            Dict of prompt type -> template

        Raises:
            ValueError: If model not found in config
        """
        configs = self._load_configs()
        models = configs.get('models', {})

        if model not in models:
            raise ValueError(f"Model not found in config: {model}")

        model_config = models[model]
        prompts = model_config.get('prompts', {})

        logger.debug(f"Loaded {len(prompts)} default prompts for {model}")
        return prompts

    def merge_prompts(
        self,
        default_prompts: Dict[str, str],
        custom_prompts: Optional[Dict[str, str]]
    ) -> Dict[str, str]:
        """
        Merge custom prompts with defaults.

        Args:
            default_prompts: Default prompt templates
            custom_prompts: Optional custom overrides

        Returns:
            Merged prompt dict (custom overrides defaults)
        """
        if not custom_prompts:
            return default_prompts.copy()

        merged = default_prompts.copy()
        merged.update(custom_prompts)

        logger.debug(f"Merged prompts: {len(custom_prompts)} custom overrides")
        return merged

    def validate_prompt(
        self,
        prompt_type: str,
        template: str,
        model: str
    ) -> ValidationResult:
        """
        Validate a custom prompt template.

        Args:
            prompt_type: Type of prompt (ocr, merge, markdown, etc.)
            template: Prompt template string
            model: Model name

        Returns:
            ValidationResult with validation status and details
        """
        warnings = []

        # Define required variables for each prompt type
        required_vars_map = {
            "ocr": ["image"],
            "markdown": ["image"],
            "merge": ["image", "embedded_text", "ocr_text"],
            "structured": ["image"],
        }

        required_vars = required_vars_map.get(prompt_type, ["image"])

        # Find all variables in template (look for {var} patterns)
        found_vars = re.findall(r'\{(\w+)\}', template)

        # Check if all required variables are present
        missing_vars = set(required_vars) - set(found_vars)
        if missing_vars:
            return ValidationResult(
                valid=False,
                warnings=[f"Missing required variables: {', '.join(missing_vars)}"],
                required_variables=required_vars,
                found_variables=found_vars
            )

        # Check template length (warn if very short or very long)
        if len(template) < 20:
            warnings.append("Prompt template is very short, may not be effective")
        elif len(template) > 2000:
            warnings.append("Prompt template is very long, may cause token limits")

        # Check if model-specific tags are present (for qwen/deepseek)
        if model.startswith("qwen") and "<|im_start|>" not in template:
            warnings.append("Qwen models typically use <|im_start|> tags in prompts")

        if model.startswith("deepseek") and "<image>" not in template:
            warnings.append("DeepSeek models require <image> tag for vision input")

        return ValidationResult(
            valid=True,
            warnings=warnings,
            required_variables=required_vars,
            found_variables=found_vars
        )

    def list_prompt_types(self) -> List[Dict[str, any]]:
        """
        List all available prompt types with metadata.

        Returns:
            List of prompt type info dicts
        """
        # Load from first available model config as reference
        configs = self._load_configs()
        models = configs.get('models', {})

        # Use qwen3-vl-8b as reference model
        reference_model = "qwen3-vl-8b"
        if reference_model in models:
            prompts = models[reference_model].get('prompts', {})
        else:
            # Fallback to first model
            first_model = next(iter(models.values()))
            prompts = first_model.get('prompts', {})

        prompt_types = []

        # Define descriptions and variables for each type
        type_metadata = {
            "ocr": {
                "description": "Basic text extraction from images",
                "variables": ["image"]
            },
            "markdown": {
                "description": "Convert document to markdown format",
                "variables": ["image"]
            },
            "merge": {
                "description": "Intelligent merging of embedded and OCR text",
                "variables": ["image", "embedded_text", "ocr_text"]
            },
            "structured": {
                "description": "Extract structured data from documents",
                "variables": ["image"]
            },
        }

        for prompt_type, template in prompts.items():
            metadata = type_metadata.get(prompt_type, {
                "description": f"{prompt_type.title()} prompt",
                "variables": ["image"]
            })

            prompt_types.append({
                "type": prompt_type,
                "description": metadata["description"],
                "default_template": template,
                "variables": metadata["variables"]
            })

        return prompt_types
