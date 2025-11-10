"""Performance and load tests."""
import pytest
import time


@pytest.mark.slow
@pytest.mark.benchmark
class TestLoadPerformance:
    """Benchmark API performance under load."""

    @pytest.mark.asyncio
    async def test_upload_performance_10_files(self, test_client, sample_pdf_path):
        """Scenario: Upload 10 files sequentially and measure performance."""
        # Arrange
        upload_times = []

        # Act
        for i in range(10):
            with open(sample_pdf_path, 'rb') as f:
                start_time = time.time()
                response = await test_client.post(
                    "/api/v1/process/upload",
                    files={"file": (f"test{i}.pdf", f, "application/pdf")}
                )
                end_time = time.time()

                assert response.status_code == 201
                upload_times.append(end_time - start_time)

        # Assert
        average_time = sum(upload_times) / len(upload_times)
        print(f"\nAverage upload time: {average_time:.3f}s")
        # Verify reasonable performance (adjust threshold as needed)
        assert average_time < 2.0  # Should be under 2 seconds per upload


@pytest.mark.slow
class TestEdgeCaseFiles:
    """Test unusual file inputs."""

    @pytest.mark.asyncio
    async def test_empty_pdf(self, test_client, test_data_dir):
        """Scenario: Upload empty PDF."""
        # Arrange
        empty_pdf = test_data_dir / "empty.pdf"

        # Act
        with open(empty_pdf, 'rb') as f:
            response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("empty.pdf", f, "application/pdf")}
            )

        # Assert - May succeed or fail gracefully
        # Empty file should be handled without crashing
        assert response.status_code in [201, 400]
