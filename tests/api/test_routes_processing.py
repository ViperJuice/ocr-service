"""Tests for Processing API routes."""
import pytest
import io
from pathlib import Path
from unittest.mock import patch, Mock

from src.api.services.job_manager import JobStatus


@pytest.mark.api
class TestFileUploadEndpoint:
    """Test POST /api/v1/process/upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_pdf_success(self, test_client, sample_pdf_path):
        """Scenario: Valid PDF upload succeeds."""
        # Arrange
        with open(sample_pdf_path, 'rb') as f:
            files = {"file": ("sample.pdf", f, "application/pdf")}

            # Act
            response = await test_client.post("/api/v1/process/upload", files=files)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "file_id" in data
        assert data["filename"] == "sample.pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["size_bytes"] > 0
        assert "uploaded_at" in data
        assert "expires_at" in data

    @pytest.mark.asyncio
    async def test_upload_image_success(self, test_client, sample_image_path):
        """Scenario: Valid image upload (JPEG) succeeds."""
        # Arrange
        with open(sample_image_path, 'rb') as f:
            files = {"file": ("sample.jpg", f, "image/jpeg")}

            # Act
            response = await test_client.post("/api/v1/process/upload", files=files)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "sample.jpg"
        assert data["mime_type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(self, test_client, test_data_dir):
        """Scenario: Upload of .txt file rejected."""
        # Arrange
        invalid_file = test_data_dir / "invalid.txt"
        with open(invalid_file, 'rb') as f:
            files = {"file": ("invalid.txt", f, "text/plain")}

            # Act
            response = await test_client.post("/api/v1/process/upload", files=files)

        # Assert
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["error"]

    @pytest.mark.asyncio
    async def test_upload_no_file(self, test_client):
        """Scenario: No file in request."""
        # Act
        response = await test_client.post("/api/v1/process/upload")

        # Assert
        assert response.status_code == 422  # Validation error


@pytest.mark.api
class TestJobSubmitEndpoint:
    """Test POST /api/v1/process/jobs endpoint."""

    @pytest.mark.asyncio
    async def test_submit_job_success(self, test_client, uploaded_file_id):
        """Scenario: Submit job with valid file_id."""
        # Arrange
        request_body = {
            "file_id": uploaded_file_id,
            "model": "deepseek-ocr",
            "output_format": "markdown"
        }

        # Act
        response = await test_client.post("/api/v1/process/jobs", json=request_body)

        # Assert
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] in ["queued", "processing"]  # Job may start immediately or be queued
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_submit_job_with_custom_prompts(self, test_client, uploaded_file_id):
        """Scenario: Submit job with custom prompts."""
        # Arrange
        request_body = {
            "file_id": uploaded_file_id,
            "model": "deepseek-ocr",
            "output_format": "markdown",
            "custom_prompts": {
                "ocr": "Custom OCR prompt with <image> tag for {image}"
            }
        }

        # Act
        response = await test_client.post("/api/v1/process/jobs", json=request_body)

        # Assert
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_submit_job_file_not_found(self, test_client):
        """Scenario: Submit job with invalid file_id."""
        # Arrange
        request_body = {
            "file_id": "non-existent-file-id",
            "model": "deepseek-ocr",
            "output_format": "markdown"
        }

        # Act
        response = await test_client.post("/api/v1/process/jobs", json=request_body)

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["error"].lower()

    @pytest.mark.asyncio
    async def test_submit_job_missing_file_id(self, test_client):
        """Scenario: Submit job without file_id."""
        # Arrange
        request_body = {
            "model": "deepseek-ocr",
            "output_format": "markdown"
        }

        # Act
        response = await test_client.post("/api/v1/process/jobs", json=request_body)

        # Assert
        assert response.status_code == 422  # Validation error


@pytest.mark.api
class TestJobStatusEndpoint:
    """Test GET /api/v1/process/jobs/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_queued_job(self, test_client, sample_pdf_path):
        """Scenario: Get status of newly created job."""
        # Arrange - Upload and submit job
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        submit_response = await test_client.post(
            "/api/v1/process/jobs",
            json={"file_id": file_id, "output_format": "markdown"}
        )
        job_id = submit_response.json()["job_id"]

        # Act
        response = await test_client.get(f"/api/v1/process/jobs/{job_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] in ["queued", "processing", "completed"]

    @pytest.mark.asyncio
    async def test_get_status_job_not_found(self, test_client):
        """Scenario: Request status for non-existent job."""
        # Act
        response = await test_client.get("/api/v1/process/jobs/non-existent-job-id")

        # Assert
        assert response.status_code == 404


@pytest.mark.api
class TestJobResultEndpoint:
    """Test GET /api/v1/process/jobs/{job_id}/result endpoint."""

    @pytest.mark.asyncio
    async def test_get_result_job_not_completed(self, test_client, sample_pdf_path):
        """Scenario: Get result of job that hasn't completed."""
        # Arrange - Create queued job
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        # Submit job - it will process in background
        submit_response = await test_client.post(
            "/api/v1/process/jobs",
            json={"file_id": file_id, "output_format": "markdown"}
        )
        job_id = submit_response.json()["job_id"]

        # Act
        response = await test_client.get(f"/api/v1/process/jobs/{job_id}/result")

        # Assert
        assert response.status_code in [409, 400]  # Conflict or Bad Request

    @pytest.mark.asyncio
    async def test_get_result_job_not_found(self, test_client):
        """Scenario: Get result for non-existent job."""
        # Act
        response = await test_client.get("/api/v1/process/jobs/non-existent-job/result")

        # Assert
        assert response.status_code == 404


@pytest.mark.api
class TestJobCancelEndpoint:
    """Test DELETE /api/v1/process/jobs/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, test_client):
        """Scenario: Cancel non-existent job."""
        # Act
        response = await test_client.delete("/api/v1/process/jobs/non-existent-job")

        # Assert
        assert response.status_code == 404
