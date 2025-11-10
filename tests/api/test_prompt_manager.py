"""Tests for PromptManager service."""
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from src.api.services.prompt_manager import PromptManager, ValidationResult


@pytest.mark.unit
class TestPromptLoading:
    """Test default prompt loading from YAML."""

    def test_load_default_prompts_deepseek(self, prompt_manager):
        """Scenario: Load default prompts for deepseek-ocr model."""
        # Act
        prompts = prompt_manager.get_default_prompts("deepseek-ocr")

        # Assert
        assert isinstance(prompts, dict)
        assert "ocr" in prompts
        assert isinstance(prompts["ocr"], str)
        assert len(prompts["ocr"]) > 0

    def test_load_default_prompts_qwen(self, prompt_manager):
        """Scenario: Load default prompts for qwen2-vl-7b model."""
        # Act
        prompts = prompt_manager.get_default_prompts("qwen2-vl-7b")

        # Assert
        assert isinstance(prompts, dict)
        assert "ocr" in prompts
        # qwen supports multiple prompt types
        assert len(prompts) >= 1
        for prompt_text in prompts.values():
            assert isinstance(prompt_text, str)
            assert len(prompt_text) > 0

    def test_load_prompts_invalid_model(self, prompt_manager):
        """Scenario: Request prompts for non-existent model."""
        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            prompt_manager.get_default_prompts("invalid-model")

        assert "not found" in str(exc_info.value).lower()

    def test_prompts_loaded_from_yaml(self, prompt_manager):
        """Scenario: Verify prompts come from config/model_configs.yaml."""
        # Act
        configs = prompt_manager._load_configs()

        # Assert
        assert "models" in configs
        assert len(configs["models"]) > 0
        # Verify structure
        for model_name, model_config in configs["models"].items():
            assert "prompts" in model_config
            assert isinstance(model_config["prompts"], dict)


@pytest.mark.unit
class TestPromptMerging:
    """Test custom prompt merging with defaults."""

    def test_merge_custom_ocr_prompt(self, prompt_manager):
        """Scenario: Custom 'ocr' prompt overrides default."""
        # Arrange
        default_prompts = {"ocr": "Default OCR", "merge": "Default Merge"}
        custom_prompts = {"ocr": "Custom OCR"}

        # Act
        merged = prompt_manager.merge_prompts(default_prompts, custom_prompts)

        # Assert
        assert merged["ocr"] == "Custom OCR"
        assert merged["merge"] == "Default Merge"

    def test_merge_multiple_custom_prompts(self, prompt_manager):
        """Scenario: Multiple custom prompts override defaults."""
        # Arrange
        default_prompts = {"ocr": "Default OCR", "merge": "Default Merge", "markdown": "Default Markdown"}
        custom_prompts = {"ocr": "Custom OCR", "merge": "Custom Merge"}

        # Act
        merged = prompt_manager.merge_prompts(default_prompts, custom_prompts)

        # Assert
        assert merged["ocr"] == "Custom OCR"
        assert merged["merge"] == "Custom Merge"
        assert merged["markdown"] == "Default Markdown"

    def test_merge_with_no_custom_prompts(self, prompt_manager):
        """Scenario: No custom prompts provided (None or {})."""
        # Arrange
        default_prompts = {"ocr": "Default OCR", "merge": "Default Merge"}

        # Act
        merged_none = prompt_manager.merge_prompts(default_prompts, None)
        merged_empty = prompt_manager.merge_prompts(default_prompts, {})

        # Assert
        assert merged_none == default_prompts
        assert merged_empty == default_prompts

    def test_merge_custom_prompt_new_key(self, prompt_manager):
        """Scenario: Custom prompt with key not in defaults."""
        # Arrange
        default_prompts = {"ocr": "Default OCR"}
        custom_prompts = {"new_prompt_type": "New prompt"}

        # Act
        merged = prompt_manager.merge_prompts(default_prompts, custom_prompts)

        # Assert
        assert "ocr" in merged
        assert "new_prompt_type" in merged
        assert merged["ocr"] == "Default OCR"
        assert merged["new_prompt_type"] == "New prompt"

    def test_merge_preserves_default_order(self, prompt_manager):
        """Scenario: Merging doesn't change prompt order (dict preserves insertion order)."""
        # Arrange
        default_prompts = {"ocr": "Default OCR", "merge": "Default Merge", "markdown": "Default Markdown"}
        custom_prompts = {"merge": "Custom Merge"}

        # Act
        merged = prompt_manager.merge_prompts(default_prompts, custom_prompts)

        # Assert
        assert list(merged.keys()) == ["ocr", "merge", "markdown"]


@pytest.mark.unit
class TestPromptValidation:
    """Test custom prompt template validation."""

    def test_validate_ocr_prompt_valid(self, prompt_manager):
        """Scenario: Valid OCR prompt with correct variables."""
        # Arrange
        template = "Extract text from this image: {image}"

        # Act
        result = prompt_manager.validate_prompt("ocr", template, "deepseek-ocr")

        # Assert
        assert result.valid is True
        assert "image" in result.required_variables
        assert "image" in result.found_variables

    def test_validate_merge_prompt_valid(self, prompt_manager):
        """Scenario: Valid merge prompt with all required variables."""
        # Arrange
        template = "Merge the following: Image={image}, Embedded={embedded_text}, OCR={ocr_text}"

        # Act
        result = prompt_manager.validate_prompt("merge", template, "qwen2-vl-7b")

        # Assert
        assert result.valid is True
        assert "image" in result.required_variables
        assert "embedded_text" in result.required_variables
        assert "ocr_text" in result.required_variables
        assert "image" in result.found_variables
        assert "embedded_text" in result.found_variables
        assert "ocr_text" in result.found_variables

    def test_validate_prompt_missing_variable(self, prompt_manager):
        """Scenario: Prompt missing required variable."""
        # Arrange - OCR prompt without {image}
        template = "Extract text from this document"

        # Act
        result = prompt_manager.validate_prompt("ocr", template, "deepseek-ocr")

        # Assert
        assert result.valid is False
        assert len(result.warnings) > 0
        assert "missing" in result.warnings[0].lower()

    def test_validate_prompt_unknown_variable(self, prompt_manager):
        """Scenario: Prompt contains undefined variable."""
        # Arrange
        template = "Extract text: {image} with {unknown_var}"

        # Act
        result = prompt_manager.validate_prompt("ocr", template, "deepseek-ocr")

        # Assert
        assert result.valid is True  # Valid because required vars are present
        # unknown_var should be in found_variables
        assert "unknown_var" in result.found_variables

    def test_validate_prompt_invalid_format(self, prompt_manager):
        """Scenario: Malformed template (missing closing brace)."""
        # Note: Python string formatting doesn't strictly validate brace matching
        # This test verifies we can still parse variables from partial templates
        template = "Text {image"

        # Act
        result = prompt_manager.validate_prompt("ocr", template, "deepseek-ocr")

        # Assert
        # The regex should not find "image" without closing brace
        assert result.valid is False  # Missing required variable

    def test_validate_model_specific_warnings(self, prompt_manager):
        """Scenario: Prompt for DeepSeek model without <image> tag."""
        # Arrange - DeepSeek prompt without <image> tag
        template = "Extract text from: {image}"

        # Act
        result = prompt_manager.validate_prompt("ocr", template, "deepseek-ocr")

        # Assert
        assert result.valid is True
        # Check for DeepSeek-specific warning
        warnings = [w.lower() for w in result.warnings]
        assert any("<image>" in w for w in warnings)


@pytest.mark.unit
class TestPromptListing:
    """Test listing available prompt types."""

    def test_list_prompt_types(self, prompt_manager):
        """Scenario: Get all available prompt types."""
        # Act
        prompt_types = prompt_manager.list_prompt_types()

        # Assert
        assert isinstance(prompt_types, list)
        assert len(prompt_types) > 0

        # Verify structure
        for prompt_info in prompt_types:
            assert "type" in prompt_info
            assert "description" in prompt_info
            assert "default_template" in prompt_info
            assert "variables" in prompt_info

    def test_list_prompt_types_with_metadata(self, prompt_manager):
        """Scenario: Get prompt types with descriptions and variables."""
        # Act
        prompt_types = prompt_manager.list_prompt_types()

        # Assert
        # Find OCR prompt type
        ocr_prompt = next((p for p in prompt_types if p["type"] == "ocr"), None)
        assert ocr_prompt is not None
        assert "description" in ocr_prompt
        assert "image" in ocr_prompt["variables"]
        assert isinstance(ocr_prompt["default_template"], str)
        assert len(ocr_prompt["default_template"]) > 0
