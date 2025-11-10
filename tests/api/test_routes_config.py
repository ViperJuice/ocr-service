"""Tests for Configuration API routes."""
import pytest


@pytest.mark.api
class TestModelsEndpoint:
    """Test GET /api/v1/config/models endpoint."""

    @pytest.mark.asyncio
    async def test_list_models_success(self, test_client):
        """Scenario: List available models."""
        # Act
        response = await test_client.get("/api/v1/config/models")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0

        # Verify structure
        for model in data["models"]:
            assert "model_id" in model
            assert "name" in model
            assert "capabilities" in model


@pytest.mark.api
class TestPromptsEndpoint:
    """Test GET /api/v1/config/prompts endpoint."""

    @pytest.mark.asyncio
    async def test_list_prompts_success(self, test_client):
        """Scenario: List available prompt types."""
        # Act
        response = await test_client.get("/api/v1/config/prompts")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "prompt_types" in data
        assert isinstance(data["prompt_types"], list)
        assert len(data["prompt_types"]) > 0

        # Verify structure
        for prompt_type in data["prompt_types"]:
            assert "type" in prompt_type
            assert "description" in prompt_type
            assert "variables" in prompt_type


@pytest.mark.api
class TestPromptValidationEndpoint:
    """Test POST /api/v1/config/prompts/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_valid_prompt(self, test_client):
        """Scenario: Validate a valid prompt."""
        # Arrange
        request_body = {
            "prompt_type": "ocr",
            "template": "Extract text from this image: {image}",
            "model": "deepseek-ocr"
        }

        # Act
        response = await test_client.post("/api/v1/config/prompts/validate", json=request_body)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
        assert data["valid"] is True
        assert "required_variables" in data
        assert "image" in data["required_variables"]

    @pytest.mark.asyncio
    async def test_validate_prompt_missing_variable(self, test_client):
        """Scenario: Validate prompt missing required variable."""
        # Arrange
        request_body = {
            "prompt_type": "ocr",
            "template": "Extract text from document",  # Missing {image}
            "model": "deepseek-ocr"
        }

        # Act
        response = await test_client.post("/api/v1/config/prompts/validate", json=request_body)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
        assert data["valid"] is False
        assert len(data.get("warnings", [])) > 0


@pytest.mark.api
class TestSettingsEndpoint:
    """Test GET /api/v1/config/settings endpoint."""

    @pytest.mark.asyncio
    async def test_get_settings_success(self, test_client):
        """Scenario: Get service settings."""
        # Act
        response = await test_client.get("/api/v1/config/settings")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "default_model" in data
        assert "default_output_format" in data
        assert "temp_file_expiry_hours" in data
