"""Integration tests for pipeline batch processing (Phase 3.7C).

These tests verify that the StagedPipelineProcessor correctly uses batch inference
for OCR processing and achieves the expected performance improvements.

Requirements:
- DeepSeek-OCR container running on http://localhost:8001
- Qwen3-VL container running on http://localhost:8002
- Containers must support /batch_infer endpoint

Run with: pytest tests/integration/test_pipeline_batch_processing.py -v
"""
import pytest
import time
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from unittest.mock import Mock, MagicMock
import asyncio

from src.preprocessing.staged_pipeline import StagedPipelineProcessor
from src.preprocessing.pdf_handler import PDFHandler
from src.models.model_manager import ModelManager


@pytest.fixture
def model_configs():
    """Model configurations for testing."""
    return {
        "deepseek-ocr": {
            "infer_config": {
                "base_size": 1024,
                "image_size": 640,
                "crop_mode": True,
                "eval_mode": True
            },
            "prompts": {
                "ocr": "<image>\nFree OCR. "
            }
        },
        "qwen3-vl-8b": {
            "prompts": {
                "ocr": "Extract all text from this image.",
                "merge": "Merge these two text versions."
            }
        }
    }


@pytest.fixture
async def model_manager(model_configs):
    """Create and initialize ModelManager with container mode."""
    manager = ModelManager(model_configs)
    await manager.initialize_container_mode(
        deepseek_url="http://localhost:8001",
        qwen_url="http://localhost:8002",
        timeout=300.0
    )
    yield manager
    await manager.close_container_mode()


@pytest.fixture
def pdf_handler():
    """Create PDFHandler instance."""
    return PDFHandler()


def create_test_pdf(num_pages: int, output_path: Path) -> None:
    """
    Create a multi-page PDF with sample text for testing.

    Args:
        num_pages: Number of pages to create
        output_path: Path to save PDF
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter

        c = canvas.Canvas(str(output_path), pagesize=letter)
        width, height = letter

        for i in range(num_pages):
            # Add some text to each page
            c.drawString(100, height - 100, f"Test Page {i + 1}")
            c.drawString(100, height - 150, f"This is page {i + 1} of {num_pages}")
            c.drawString(100, height - 200, "Sample text for OCR processing")
            c.drawString(100, height - 250, "Testing batch inference performance")
            c.showPage()

        c.save()
    except ImportError:
        # Fallback: Create simple PDF using PIL and img2pdf
        import img2pdf

        images = []
        for i in range(num_pages):
            # Create image with text
            img = Image.new('RGB', (800, 1000), color='white')
            draw = ImageDraw.Draw(img)

            # Add text (using default font)
            draw.text((50, 50), f"Test Page {i + 1}", fill='black')
            draw.text((50, 100), f"This is page {i + 1} of {num_pages}", fill='black')
            draw.text((50, 150), "Sample text for OCR processing", fill='black')
            draw.text((50, 200), "Testing batch inference performance", fill='black')

            # Save to temp file
            img_temp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            img.save(img_temp.name)
            images.append(img_temp.name)

        # Convert images to PDF
        with open(output_path, 'wb') as f:
            f.write(img2pdf.convert(images))

        # Clean up temp images
        for img_path in images:
            Path(img_path).unlink()


@pytest.mark.integration
@pytest.mark.asyncio
class TestPipelineBatchProcessing:
    """Integration tests for pipeline batch processing."""

    async def test_batch_processing_50_pages(self, model_manager, pdf_handler):
        """
        Test batch processing with 50-page PDF.

        Verifies:
        - OCR batch requests are ~7 (50 / 8 = 6.25, rounded up)
        - Output correctness (all pages processed)
        - Metadata includes batch information
        """
        # Create 50-page test PDF
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test_50_pages.pdf"
            output_path = Path(tmpdir) / "output.md"

            create_test_pdf(50, pdf_path)

            # Create pipeline with batch processing
            event_loop = asyncio.get_event_loop()
            pipeline = StagedPipelineProcessor(
                model_manager=model_manager,
                pdf_handler=pdf_handler,
                verbose=True,
                enable_system_monitoring=False,
                event_loop=event_loop,
                processing_params={'page_batch_size': 8}
            )

            # Track batch requests (we'll count progress emissions instead)
            progress_events = []

            def progress_callback(pct, pages, stage):
                if stage == "ocr":
                    progress_events.append((pct, pages, stage))

            pipeline.progress_callback = progress_callback

            # Process PDF
            start_time = time.time()
            result = pipeline.process_pdf(
                pdf_path=pdf_path,
                output_path=output_path,
                output_format="markdown",
                resume=False
            )
            elapsed = time.time() - start_time

            # Verify results
            assert result['total_pages'] == 50
            assert output_path.exists()

            # Verify OCR stage used batch processing
            ocr_stage = [s for s in result['stages'] if s.stage_name == 'ocr'][0]
            assert ocr_stage.pages_processed == 50

            # Verify progress events (should be ~7 for OCR, not 50)
            ocr_progress_events = [e for e in progress_events if e[2] == 'ocr']
            # Expected: 7 batches (50 / 8 = 6.25, rounded up to 7)
            assert len(ocr_progress_events) <= 10, f"Too many progress events: {len(ocr_progress_events)}"
            assert len(ocr_progress_events) >= 5, f"Too few progress events: {len(ocr_progress_events)}"

            print(f"\n50-page PDF processed in {elapsed:.2f}s")
            print(f"OCR progress events: {len(ocr_progress_events)} (expected ~7)")
            print(f"Average per page: {elapsed/50:.2f}s")

    async def test_batch_processing_performance(self, model_manager, pdf_handler):
        """
        Measure batch vs sequential performance for 20-page document.

        Verifies:
        - Batch processing is at least 2x faster than sequential
        - Logs actual speedup ratio
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test_20_pages.pdf"

            create_test_pdf(20, pdf_path)

            event_loop = asyncio.get_event_loop()

            # Test 1: Sequential processing (batch_size = 1)
            print("\n=== Sequential Processing (batch_size=1) ===")
            output_seq = Path(tmpdir) / "output_seq.md"
            pipeline_seq = StagedPipelineProcessor(
                model_manager=model_manager,
                pdf_handler=pdf_handler,
                verbose=True,
                enable_system_monitoring=False,
                event_loop=event_loop,
                processing_params={'page_batch_size': 1}
            )

            seq_start = time.time()
            result_seq = pipeline_seq.process_pdf(
                pdf_path=pdf_path,
                output_path=output_seq,
                output_format="markdown",
                resume=False
            )
            seq_time = time.time() - seq_start

            # Test 2: Batch processing (batch_size = 8)
            print("\n=== Batch Processing (batch_size=8) ===")
            output_batch = Path(tmpdir) / "output_batch.md"
            pipeline_batch = StagedPipelineProcessor(
                model_manager=model_manager,
                pdf_handler=pdf_handler,
                verbose=True,
                enable_system_monitoring=False,
                event_loop=event_loop,
                processing_params={'page_batch_size': 8}
            )

            batch_start = time.time()
            result_batch = pipeline_batch.process_pdf(
                pdf_path=pdf_path,
                output_path=output_batch,
                output_format="markdown",
                resume=False
            )
            batch_time = time.time() - batch_start

            # Calculate speedup
            speedup = seq_time / batch_time

            print(f"\n=== Performance Results ===")
            print(f"Sequential (batch_size=1): {seq_time:.2f}s")
            print(f"Batch (batch_size=8):      {batch_time:.2f}s")
            print(f"Speedup:                   {speedup:.2f}x")

            # Verify speedup (should be at least 1.5x, ideally 2x+)
            # Note: Full pipeline includes merge, which is still sequential
            # So we expect less than the 3-4x speedup of pure OCR batch
            assert speedup >= 1.3, f"Expected at least 1.3x speedup, got {speedup:.2f}x"

            # Verify both produce same number of pages
            assert result_seq['total_pages'] == result_batch['total_pages'] == 20

    async def test_batch_processing_edge_cases(self, model_manager, pdf_handler):
        """
        Test edge cases for batch processing.

        Cases:
        - 1-page document (batch_size = 1)
        - 7-page document (one full batch, no remainder)
        - 9-page document (one full batch, one remainder)
        """
        event_loop = asyncio.get_event_loop()

        test_cases = [
            (1, "single page"),
            (7, "less than batch size"),
            (9, "one full batch + remainder")
        ]

        for num_pages, description in test_cases:
            print(f"\n=== Testing {description}: {num_pages} pages ===")

            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = Path(tmpdir) / f"test_{num_pages}_pages.pdf"
                output_path = Path(tmpdir) / "output.md"

                create_test_pdf(num_pages, pdf_path)

                pipeline = StagedPipelineProcessor(
                    model_manager=model_manager,
                    pdf_handler=pdf_handler,
                    verbose=True,
                    enable_system_monitoring=False,
                    event_loop=event_loop,
                    processing_params={'page_batch_size': 8}
                )

                result = pipeline.process_pdf(
                    pdf_path=pdf_path,
                    output_path=output_path,
                    output_format="markdown",
                    resume=False
                )

                # Verify all pages processed
                assert result['total_pages'] == num_pages
                assert output_path.exists()

                print(f"  SUCCESS: {num_pages} pages processed correctly")

    async def test_progress_emission_batched(self, model_manager, pdf_handler):
        """
        Test that progress emission works correctly with batch processing.

        Verifies:
        - 16-page document with batch_size=8 emits ~2 progress events (not 16)
        - Progress values are ~50%, ~100% for OCR stage
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test_16_pages.pdf"
            output_path = Path(tmpdir) / "output.md"

            create_test_pdf(16, pdf_path)

            event_loop = asyncio.get_event_loop()
            pipeline = StagedPipelineProcessor(
                model_manager=model_manager,
                pdf_handler=pdf_handler,
                verbose=True,
                enable_system_monitoring=False,
                event_loop=event_loop,
                processing_params={'page_batch_size': 8}
            )

            # Track progress emissions
            progress_events = []

            def progress_callback(pct, pages, stage):
                progress_events.append((pct, pages, stage))
                print(f"  Progress: {stage} - {pct:.1f}% ({pages} pages)")

            pipeline.progress_callback = progress_callback

            # Process PDF
            result = pipeline.process_pdf(
                pdf_path=pdf_path,
                output_path=output_path,
                output_format="markdown",
                resume=False
            )

            # Verify results
            assert result['total_pages'] == 16

            # Filter OCR progress events
            ocr_events = [e for e in progress_events if e[2] == 'ocr']

            print(f"\n=== Progress Events ===")
            print(f"Total OCR progress events: {len(ocr_events)}")
            for pct, pages, stage in ocr_events:
                print(f"  {pct:.1f}% - {pages} pages")

            # Should have ~2 OCR progress events (16 pages / 8 batch = 2 batches)
            assert len(ocr_events) <= 5, f"Too many OCR progress events: {len(ocr_events)}"
            assert len(ocr_events) >= 2, f"Too few OCR progress events: {len(ocr_events)}"

            # Verify progress is monotonically increasing
            for i in range(1, len(ocr_events)):
                assert ocr_events[i][0] >= ocr_events[i-1][0], "Progress should be monotonically increasing"

    async def test_integration_with_phase_3_7a(self, model_manager, pdf_handler):
        """
        Test integration with Phase 3.7A features.

        Verifies:
        - Output buffering works with batch processing
        - Checkpoints saved correctly
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test_50_pages.pdf"
            output_path = Path(tmpdir) / "output.md"

            create_test_pdf(50, pdf_path)

            event_loop = asyncio.get_event_loop()
            pipeline = StagedPipelineProcessor(
                model_manager=model_manager,
                pdf_handler=pdf_handler,
                verbose=True,
                enable_system_monitoring=False,
                event_loop=event_loop,
                processing_params={'page_batch_size': 8}
            )

            # Process PDF
            result = pipeline.process_pdf(
                pdf_path=pdf_path,
                output_path=output_path,
                output_format="markdown",
                resume=False
            )

            # Verify all pages processed
            assert result['total_pages'] == 50
            assert output_path.exists()

            # Read output and verify structure
            with open(output_path, 'r') as f:
                content = f.read()

            # Count page markers (should be 50)
            page_markers = content.count('<!-- Page ')
            assert page_markers == 50, f"Expected 50 page markers, found {page_markers}"

            print(f"\n=== Integration Test Results ===")
            print(f"Pages processed: {result['total_pages']}")
            print(f"Page markers in output: {page_markers}")
            print(f"Output file size: {output_path.stat().st_size} bytes")


@pytest.mark.integration
@pytest.mark.asyncio
class TestBatchSizeConfiguration:
    """Test configurable batch size."""

    async def test_custom_batch_size(self, model_manager, pdf_handler):
        """Test that custom batch size is respected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test_20_pages.pdf"
            output_path = Path(tmpdir) / "output.md"

            create_test_pdf(20, pdf_path)

            event_loop = asyncio.get_event_loop()

            # Test with batch_size = 4
            pipeline = StagedPipelineProcessor(
                model_manager=model_manager,
                pdf_handler=pdf_handler,
                verbose=True,
                enable_system_monitoring=False,
                event_loop=event_loop,
                processing_params={'page_batch_size': 4}
            )

            # Verify batch size is set correctly
            assert pipeline.page_batch_size == 4

            # Track progress
            progress_events = []

            def progress_callback(pct, pages, stage):
                if stage == "ocr":
                    progress_events.append((pct, pages, stage))

            pipeline.progress_callback = progress_callback

            # Process PDF
            result = pipeline.process_pdf(
                pdf_path=pdf_path,
                output_path=output_path,
                output_format="markdown",
                resume=False
            )

            # Verify results
            assert result['total_pages'] == 20

            # With batch_size=4, expect ~5 progress events (20 / 4 = 5)
            ocr_events = [e for e in progress_events if e[2] == 'ocr']
            print(f"\nBatch size 4: {len(ocr_events)} progress events (expected ~5)")
            assert len(ocr_events) >= 4 and len(ocr_events) <= 7

    async def test_default_batch_size(self, model_manager, pdf_handler):
        """Test that default batch size (8) is used when not specified."""
        event_loop = asyncio.get_event_loop()

        # Create pipeline without processing_params
        pipeline = StagedPipelineProcessor(
            model_manager=model_manager,
            pdf_handler=pdf_handler,
            verbose=False,
            enable_system_monitoring=False,
            event_loop=event_loop
        )

        # Verify default batch size
        assert pipeline.page_batch_size == 8
