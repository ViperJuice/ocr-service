"""Tests for File API routes."""
import pytest


@pytest.mark.api
class TestFileMetadataEndpoint:
    """Test GET /api/v1/files/{file_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_file_metadata_success(self, test_client, sample_pdf_path):
        """Scenario: Retrieve metadata for existing file."""
        # Arrange - Upload file first
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("sample.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        # Act
        response = await test_client.get(f"/api/v1/files/{file_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == file_id
        assert data["filename"] == "sample.pdf"
        assert "size_bytes" in data
        assert "uploaded_at" in data

    @pytest.mark.asyncio
    async def test_get_file_metadata_not_found(self, test_client):
        """Scenario: Request metadata for non-existent file."""
        # Act
        response = await test_client.get("/api/v1/files/non-existent-file-id")

        # Assert
        assert response.status_code == 404


@pytest.mark.api
class TestFileDeleteEndpoint:
    """Test DELETE /api/v1/files/{file_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_file_success(self, test_client, sample_pdf_path):
        """Scenario: Delete existing file."""
        # Arrange - Upload file first
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("sample.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        # Act
        response = await test_client.delete(f"/api/v1/files/{file_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True

        # Verify file is gone
        get_response = await test_client.get(f"/api/v1/files/{file_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, test_client):
        """Scenario: Delete non-existent file."""
        # Act
        response = await test_client.delete("/api/v1/files/non-existent-file-id")

        # Assert
        assert response.status_code == 404
