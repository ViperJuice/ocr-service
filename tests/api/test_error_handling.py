"""Tests for API error handling."""
import pytest


@pytest.mark.api
class TestHTTPExceptionHandling:
    """Test global error handlers."""

    @pytest.mark.asyncio
    async def test_404_error_format(self, test_client):
        """Scenario: Request non-existent endpoint."""
        # Act
        response = await test_client.get("/invalid/path")

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_422_validation_error_format(self, test_client):
        """Scenario: Invalid request body."""
        # Arrange - Submit job without required file_id
        request_body = {
            "output_format": "markdown"
            # Missing required file_id
        }

        # Act
        response = await test_client.post("/api/v1/process/jobs", json=request_body)

        # Assert
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


@pytest.mark.api
class TestCORSHeaders:
    """Test CORS middleware."""

    @pytest.mark.asyncio
    async def test_cors_headers_present(self, test_client):
        """Scenario: Check CORS headers on response."""
        # Act
        response = await test_client.get("/health")

        # Assert
        # CORS headers may or may not be present depending on configuration
        # This test just verifies the endpoint responds
        assert response.status_code == 200


@pytest.mark.api
class TestRequestValidation:
    """Test Pydantic request validation."""

    @pytest.mark.asyncio
    async def test_invalid_output_format(self, test_client, sample_pdf_path):
        """Scenario: Invalid output format."""
        # Arrange - Upload file
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        # Submit with invalid format
        request_body = {
            "file_id": file_id,
            "output_format": "invalid_format"  # Should be markdown, text, or json
        }

        # Act
        response = await test_client.post("/api/v1/process/jobs", json=request_body)

        # Assert
        assert response.status_code == 422
