"""Staged pipeline processor for eliminating model-switching fragmentation."""
from typing import List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
import time
import logging
import asyncio
import io
import base64
from PIL import Image

from .pdf_handler import PDFHandler
from .checkpoint_manager import CheckpointManager
from .intermediate_cache import IntermediateCache, OCRPageResult
from ..utils.system_monitor import SystemMonitor
from ..utils.snapshot_accumulator import SnapshotAccumulator

# Phase 4 + BAML: Import generated BAML client
from baml_client_py.baml_client import b
import baml_py

logger = logging.getLogger(__name__)


def run_async_in_thread(coro, event_loop=None):
    """
    Run async coroutine in a thread-safe manner.

    Args:
        coro: The coroutine to run
        event_loop: Optional event loop to use (recommended for thread-safety)

    Returns:
        Result of the coroutine

    Note:
        If event_loop is provided, uses asyncio.run_coroutine_threadsafe for proper
        thread-safe execution. Otherwise falls back to creating a new loop (not recommended).
    """
    if event_loop is not None:
        # Thread-safe execution using the main event loop
        future = asyncio.run_coroutine_threadsafe(coro, event_loop)
        return future.result()  # Block until complete
    else:
        # Fallback: Create new loop (may cause issues with httpx clients)
        logger.warning("run_async_in_thread called without event_loop - creating new loop")
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            result = new_loop.run_until_complete(coro)
            # Allow pending tasks to complete before closing
            pending = asyncio.all_tasks(new_loop)
            if pending:
                new_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            return result
        finally:
            # Give the loop a moment to clean up
            new_loop.run_until_complete(asyncio.sleep(0))
            new_loop.close()
            asyncio.set_event_loop(None)


def async_generator_to_sync(async_gen, event_loop):
    """
    Convert an async generator to a sync generator using an event loop.

    Args:
        async_gen: The async generator to convert
        event_loop: Event loop to run the async operations in

    Yields:
        Items from the async generator
    """
    async def _get_next():
        """Get next item from async generator."""
        try:
            return await async_gen.__anext__()
        except StopAsyncIteration:
            return None

    while True:
        future = asyncio.run_coroutine_threadsafe(_get_next(), event_loop)
        item = future.result()
        if item is None:
            break
        yield item


def resize_image_for_merge(image: Image.Image, max_dimension: int = 1024) -> Image.Image:
    """
    Resize image if it exceeds max_dimension to prevent CUDA OOM in Qwen merge model.

    Args:
        image: PIL Image to potentially resize
        max_dimension: Maximum width or height (default: 1024px)

    Returns:
        Resized image if original was too large, otherwise original image

    Note:
        Qwen3-VL has limited GPU memory. Large images (2481x3508 from legal PDFs at 300 DPI)
        cause OOM during attention calculation. Resizing to ~1024px significantly reduces
        memory usage while preserving enough detail for text merging.
    """
    width, height = image.size
    max_current = max(width, height)

    if max_current <= max_dimension:
        logger.debug(f"Image size {width}x{height} within limit ({max_dimension}px), no resize needed")
        return image

    # Calculate resize ratio to fit within max_dimension
    ratio = max_dimension / max_current
    new_width = int(width * ratio)
    new_height = int(height * ratio)

    logger.info(f"Resizing image from {width}x{height} to {new_width}x{new_height} "
                f"(max_dimension={max_dimension}) to prevent Qwen OOM")

    # Use LANCZOS for high-quality downsampling
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return resized


def pil_to_baml_image(pil_image: Image.Image) -> baml_py.Image:
    """Convert PIL Image to BAML Image format.

    Args:
        pil_image: PIL Image object

    Returns:
        BAML Image object (base64-encoded PNG)

    Note:
        BAML's OpenAI-compatible provider expects images in base64 format.
        This function converts PIL Images to PNG format and encodes as base64.
    """
    buffer = io.BytesIO()
    pil_image.save(buffer, format='PNG')
    b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return baml_py.Image.from_base64('png', b64)


@dataclass
class StageResult:
    """Result from a pipeline stage."""
    stage_name: str
    pages_processed: int
    total_time: float
    model_used: str
    strategy_used: str
    avg_page_time: float


class StagedPipelineProcessor:
    """
    Process PDFs using staged pipeline approach.

    Stage 1: OCR all pages with DeepSeek-OCR
    Stage 2: Merge all pages with Qwen3-VL

    Benefits:
    - Eliminates model-switching fragmentation
    - Each stage can use optimal GPU strategy
    - Full resume capability within any stage
    """

    # Phase 3.7A: I/O Optimization constants
    OUTPUT_BUFFER_SIZE = 10  # Buffer 10 pages before writing to disk

    # Phase 3.7C: Batch processing constants
    DEFAULT_PAGE_BATCH_SIZE = 8  # Optimal balance for GPU memory and throughput
    """
    Default batch size for page processing (Phase 3.7C).

    Batch size considerations:
    - 4: Lower GPU memory usage, more API requests (conservative)
    - 8: Optimal balance - recommended for most use cases
    - 16: Maximum batch size, higher GPU memory usage (aggressive)

    Can be overridden via processing_params['page_batch_size']
    """

    def __init__(
        self,
        model_manager,
        pdf_handler: PDFHandler,
        baml_ocr_service: Optional[Any] = None,
        pipeline_coordinator: Optional[Any] = None,
        verbose: bool = False,
        enable_memory_profiling: bool = False,
        enable_system_monitoring: bool = True,
        monitor_interval: int = 30,
        prefer_quality: bool = True,
        progress_callback: Optional[Any] = None,
        result_emitter: Optional[Any] = None,
        job_id: Optional[str] = None,
        event_loop=None,
        job_repository=None,
        streaming_repository=None,
        processing_params: Optional[Dict] = None
    ):
        """
        Initialize staged pipeline processor.

        Args:
            model_manager: ModelManager instance
            pdf_handler: PDFHandler instance
            baml_ocr_service: Optional BAMLOCRService for type-safe operations
            pipeline_coordinator: Optional PipelineCoordinator for container orchestration
            verbose: Print progress messages
            enable_memory_profiling: Enable memory profiling
            enable_system_monitoring: Enable system resource monitoring
            monitor_interval: Monitoring interval in seconds
            prefer_quality: Prefer quality over speed
            progress_callback: Optional callback function(progress_pct, pages_completed, stage)
            result_emitter: Optional ResultEmitter for streaming results
            job_id: Optional job identifier for result emission
            event_loop: Optional event loop for thread-safe async operations
            job_repository: Optional JobRepository for bulk DB inserts (Phase 3.7A)
            streaming_repository: Optional StreamingTokenRepository for Phase 4 database streaming
            processing_params: Optional processing parameters (Phase 3.7C: page_batch_size)
        """
        self.model_manager = model_manager
        self.pdf_handler = pdf_handler
        self.baml_ocr_service = baml_ocr_service
        self.pipeline_coordinator = pipeline_coordinator
        self.verbose = verbose
        self.enable_memory_profiling = enable_memory_profiling
        self.enable_system_monitoring = enable_system_monitoring
        self.monitor_interval = monitor_interval
        self.prefer_quality = prefer_quality
        self.progress_callback = progress_callback
        self.result_emitter = result_emitter
        self.job_id = job_id
        self._event_loop = event_loop
        self.job_repository = job_repository
        self.streaming_repository = streaming_repository

        # Phase 3.7C: Configure batch size from processing_params
        self.page_batch_size = (
            processing_params.get('page_batch_size', self.DEFAULT_PAGE_BATCH_SIZE)
            if processing_params
            else self.DEFAULT_PAGE_BATCH_SIZE
        )

        # Will be initialized in process_pdf()
        self.checkpoint_manager = None
        self.intermediate_cache = None
        self.system_monitor = None

    def _emit_progress(self, progress_pct: float, pages_completed: int, stage: str) -> None:
        """
        Emit progress if callback is set.

        Args:
            progress_pct: Progress percentage (0-100)
            pages_completed: Number of pages completed
            stage: Current processing stage
        """
        if self.progress_callback:
            try:
                self.progress_callback(progress_pct, pages_completed, stage)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")

    def process_pdf(
        self,
        pdf_path: Path,
        output_path: Path,
        max_pages: Optional[int] = None,
        dpi: int = 300,
        output_format: str = "markdown",
        resume: bool = True,
        job_id: Optional[str] = None,
        prompts: Optional[Dict[str, str]] = None,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process PDF through staged pipeline.

        Args:
            pdf_path: Path to PDF file
            output_path: Path to output file
            max_pages: Maximum pages to process (for testing, legacy)
            dpi: DPI for image extraction
            output_format: Output format ("markdown", "text", "json")
            resume: Whether to resume from checkpoint
            job_id: Optional job ID for API correlation
            prompts: Optional custom prompts to override defaults
            start_page: Starting page number (1-indexed, None = first page)
            end_page: Ending page number (1-indexed, None = last page)

        Returns:
            Dict with processing results:
            {
                'total_pages': int,
                'total_time': float,
                'stages': List[StageResult],
                'output_path': Path
            }
        """
        # Store prompts for use in processing stages
        self.custom_prompts = prompts
        # Initialize checkpoint manager
        processing_params = {
            'dpi': dpi,
            'method': 'staged_hybrid',
            'format': output_format
        }
        self.checkpoint_manager = CheckpointManager(
            output_path,
            pdf_path,
            processing_params
        )

        # Set up intermediate cache directory
        cache_dir = output_path.parent / f"{output_path.stem}.ocr_cache"
        self.intermediate_cache = IntermediateCache(cache_dir)
        self.checkpoint_manager.set_intermediate_cache_dir(cache_dir)

        # Initialize system monitor
        if self.enable_system_monitoring:
            self.system_monitor = SystemMonitor(output_path, interval=self.monitor_interval, job_id=job_id)
            self.system_monitor.start()

        # Container mode: Use simplified config
        if self.verbose:
            print("\n[Container Mode] Using containerized inference servers")

        stage_configs = {
            "ocr": {
                "model_name": "deepseek-ocr",
                "strategy_type": "container",
                "quality_score": 100.0,
                "actual_peak_gb": 0.0,
                "resolution_mode": "quality" if self.prefer_quality else "standard",
                "crop_mode": True
            },
            "merge": {
                "model_name": "qwen3-vl-8b" if self.prefer_quality else "qwen3-vl-4b",
                "strategy_type": "container",
                "quality_score": 100.0,
                "actual_peak_gb": 0.0
            }
        }

        if self.verbose:
            print(f"  OCR: {stage_configs['ocr']['model_name']} (container)")
            print(f"  MERGE: {stage_configs['merge']['model_name']} (container)")

        # Extract PDF data
        pages_data = self.pdf_handler.extract_hybrid_data(
            pdf_path, max_pages, dpi, start_page, end_page
        )
        total_pages = len(pages_data)

        # Determine where to start
        if resume:
            current_stage = self.checkpoint_manager.get_current_stage()
        else:
            current_stage = "ocr"

        results = []
        overall_start = time.time()

        try:
            # Container orchestration: Start pipeline (start DeepSeek container)
            if self.pipeline_coordinator and self._event_loop:
                from .pipeline_coordinator import StageTransitionEvent, PipelineStage
                event = StageTransitionEvent(
                    from_stage=None,
                    to_stage=PipelineStage.INIT,
                    timestamp=time.time()
                )
                run_async_in_thread(
                    self.pipeline_coordinator.on_pipeline_start(event),
                    self._event_loop
                )

            # Stage 1: OCR
            if current_stage in ["ocr", None]:
                if self.verbose:
                    print(f"\n{'='*60}")
                    print(f"STAGE 1: OCR Extraction ({total_pages} pages)")
                    print(f"{'='*60}")

                stage1_result = self._run_ocr_stage(
                    pages_data=pages_data,
                    stage_config=stage_configs["ocr"],
                    dpi=dpi,
                    resume=resume
                )
                results.append(stage1_result)

                # Mark stage complete
                self.checkpoint_manager.complete_stage("ocr")

                # Emit stage complete
                if self.result_emitter and self.job_id:
                    self.result_emitter.emit_stage_complete(self.job_id, "ocr")

                # Container orchestration: Transition OCR→Merge (stop DeepSeek, start Qwen)
                if self.pipeline_coordinator and self._event_loop:
                    from .pipeline_coordinator import StageTransitionEvent, PipelineStage
                    event = StageTransitionEvent(
                        from_stage=PipelineStage.OCR,
                        to_stage=PipelineStage.MERGE,
                        timestamp=time.time()
                    )
                    run_async_in_thread(
                        self.pipeline_coordinator.on_ocr_complete(event),
                        self._event_loop
                    )

            # Stage 2: Merge
            if self.verbose:
                print(f"\n{'='*60}")
                print(f"STAGE 2: Merge & Format ({total_pages} pages)")
                print(f"{'='*60}")

            stage2_result = self._run_merge_stage(
                pages_data=pages_data,
                stage_config=stage_configs["merge"],
                output_path=output_path,
                output_format=output_format,
                dpi=dpi,
                resume=resume
            )
            results.append(stage2_result)

            # Mark stage complete
            self.checkpoint_manager.complete_stage("merge")

            # Emit stage complete
            if self.result_emitter and self.job_id:
                self.result_emitter.emit_stage_complete(self.job_id, "merge")

            # Clear checkpoint and cache on success
            self.checkpoint_manager.clear()
            self.intermediate_cache.clear()

            # Emit final completion (100%)
            self._emit_progress(100.0, total_pages, "complete")

            # Emit job complete
            if self.result_emitter and self.job_id:
                self.result_emitter.emit_job_complete(self.job_id)

            # Container orchestration: Pipeline complete (stop Qwen container)
            if self.pipeline_coordinator and self._event_loop:
                from .pipeline_coordinator import StageTransitionEvent, PipelineStage
                event = StageTransitionEvent(
                    from_stage=PipelineStage.MERGE,
                    to_stage=PipelineStage.COMPLETE,
                    timestamp=time.time()
                )
                run_async_in_thread(
                    self.pipeline_coordinator.on_pipeline_complete(event),
                    self._event_loop
                )

            total_time = time.time() - overall_start

            if self.verbose:
                print(f"\n{'='*60}")
                print(f"PIPELINE COMPLETE")
                print(f"{'='*60}")
                print(f"Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
                print(f"Average per page: {total_time/total_pages:.2f}s")
                for stage in results:
                    print(f"\n{stage.stage_name.upper()}:")
                    print(f"  Model: {stage.model_used}")
                    print(f"  Strategy: {stage.strategy_used}")
                    print(f"  Time: {stage.total_time:.1f}s ({stage.total_time/60:.1f} min)")
                    print(f"  Avg/page: {stage.avg_page_time:.2f}s")

            return {
                'total_pages': total_pages,
                'total_time': total_time,
                'stages': results,
                'output_path': output_path
            }

        except Exception as pipeline_error:
            # Container orchestration: Handle pipeline error (emergency cleanup)
            if self.pipeline_coordinator and self._event_loop:
                from .pipeline_coordinator import PipelineStage
                try:
                    # Determine current stage for error context
                    error_stage = PipelineStage.MERGE if current_stage == "merge" else PipelineStage.OCR
                    run_async_in_thread(
                        self.pipeline_coordinator.on_error(pipeline_error, error_stage),
                        self._event_loop
                    )
                except Exception as cleanup_error:
                    logger.warning(f"Error during emergency container cleanup: {cleanup_error}")

            # Re-raise the original error
            raise

        finally:
            # Cleanup (always attempt, even on error)
            try:
                if self.system_monitor:
                    self.system_monitor.stop()
            except Exception as e:
                logger.warning(f"Error stopping system monitor: {e}")

            # Phase 3.7A: Clean up job cache directory
            try:
                if self.job_id and self.intermediate_cache:
                    cache_dir = self.intermediate_cache.cache_dir
                    if cache_dir and cache_dir.exists():
                        import shutil
                        shutil.rmtree(cache_dir, ignore_errors=True)
                        logger.debug(f"Cleaned up job cache: {cache_dir}")
            except Exception as e:
                logger.warning(f"Error cleaning up job cache: {e}")

    def _run_ocr_stage(
        self,
        pages_data: List,
        stage_config: Dict[str, Any],
        dpi: int,
        resume: bool
    ) -> StageResult:
        """
        Run Stage 1: OCR extraction for all pages.

        Args:
            pages_data: List of (embedded_text, image, has_text) tuples
            stage_config: Validated configuration for OCR stage
            dpi: DPI setting
            resume: Whether to resume from checkpoint

        Returns:
            StageResult with stage metrics
        """
        # Container mode: Initialize HTTP client
        if self.model_manager.http_client_manager is None:
            logger.info("Initializing container mode for OCR stage...")
            if self._event_loop is not None:
                future = asyncio.run_coroutine_threadsafe(
                    self.model_manager.initialize_container_mode(),
                    self._event_loop
                )
                future.result()  # Block until complete
            else:
                logger.warning("No event loop provided - using asyncio.run (may cause issues)")
                asyncio.run(self.model_manager.initialize_container_mode())

        if self.system_monitor:
            self.system_monitor.set_model_info(
                model_type=stage_config["model_name"],
                model_id="container",
                device_map=None
            )

        # Update system monitor
        if self.system_monitor:
            self.system_monitor.set_active_stage(
                stage_name="ocr",
                stage_total_pages=len(pages_data),
                loaded_models=[stage_config["model_name"]]
            )

        # Determine start page
        start_page = 0
        if resume:
            start_page = self.checkpoint_manager.get_stage_resume_page("ocr")
            if self.verbose and start_page > 0:
                print(f"[Resume] Starting from page {start_page + 1}")

        total_pages = len(pages_data)
        stage_start = time.time()

        # Phase 3.7C: Process pages in batches for OCR
        if self.verbose:
            print(f"[OCR] Processing {total_pages} pages in batches of {self.page_batch_size}")

        for batch_start in range(start_page, total_pages, self.page_batch_size):
            batch_end = min(batch_start + self.page_batch_size, total_pages)
            batch_page_nums = list(range(batch_start, batch_end))
            batch_size = len(batch_page_nums)

            if self.verbose:
                progress_pct = (batch_end / total_pages) * 100
                print(f"\n[OCR] Batch {batch_start // self.page_batch_size + 1}: "
                      f"Pages {batch_start + 1}-{batch_end} ({progress_pct:.1f}%)")

            # Extract images for batch
            batch_images = []
            for page_num in batch_page_nums:
                embedded_text, image, has_text = pages_data[page_num]
                batch_images.append(image)

            # Batch OCR inference (MULTIPLE images at once)
            batch_start_time = time.time()

            # Emit inference start for first page in batch
            if self.result_emitter:
                self.result_emitter.emit_inference_start(self.job_id, batch_start, "ocr")
                self.result_emitter.emit_system_message(
                    self.job_id,
                    f"Starting batch OCR inference for pages {batch_start}-{batch_end - 1} ({batch_size} pages)...",
                    {"batch_start": batch_start, "batch_end": batch_end - 1, "batch_size": batch_size, "stage": "ocr"}
                )

            # Phase 4 + BAML: Use BAML client for per-page OCR (no batch support in BAML)
            ocr_results = []
            for idx, pil_image in enumerate(batch_images):
                page_num = batch_page_nums[idx]
                page_start_time = time.time()

                try:
                    # Convert PIL Image to BAML format
                    baml_image = pil_to_baml_image(pil_image)

                    # Call BAML ExtractTextOCR function
                    ocr_text = run_async_in_thread(
                        b.ExtractTextOCR(
                            page_image=baml_image,
                            custom_prompt=self.custom_prompts.get("ocr")
                        ),
                        event_loop=self._event_loop
                    )

                    # BAML now returns string directly
                    page_time = time.time() - page_start_time

                    # Create internal result format
                    internal_result = OCRPageResult(
                        page_num=page_num,
                        ocr_text=ocr_text or "",
                        method="ocr",
                        processing_time=page_time,
                        metadata={
                            'model': stage_config["model_name"],
                            'resolution_mode': stage_config.get("resolution_mode"),
                            'crop_mode': stage_config.get("crop_mode"),
                            'batch_mode': False,  # BAML doesn't support batch
                            'via_baml': True
                        }
                    )
                    ocr_results.append(internal_result)

                except Exception as e:
                    logger.error(f"BAML OCR failed for page {page_num}: {e}")
                    # Create error result
                    page_time = time.time() - page_start_time
                    error_result = OCRPageResult(
                        page_num=page_num,
                        ocr_text="",
                        method="ocr",
                        processing_time=page_time,
                        metadata={
                            'error': str(e),
                            'via_baml': True,
                            'model': stage_config["model_name"]
                        }
                    )
                    ocr_results.append(error_result)

            batch_time = time.time() - batch_start_time

            # Emit inference complete for batch
            if self.result_emitter:
                self.result_emitter.emit_inference_complete(self.job_id, batch_start, "ocr", batch_time)
                self.result_emitter.emit_system_message(
                    self.job_id,
                    f"Completed batch OCR in {batch_time:.2f}s ({batch_time/batch_size:.2f}s per page)",
                    {"batch_start": batch_start, "batch_end": batch_end - 1, "duration": batch_time, "stage": "ocr"}
                )

            # Process each result (already in OCRPageResult format from BAML integration)
            for idx, ocr_result in enumerate(ocr_results):
                page_num = ocr_result.page_num
                page_number = page_num + 1
                ocr_text = ocr_result.ocr_text
                page_time = ocr_result.processing_time

                # Update page timing in monitor
                if self.system_monitor:
                    self.system_monitor.update_page_timing(batch_start_time + (idx * page_time))

                # Update monitor
                if self.system_monitor:
                    overall_pct = (page_num + 1) / total_pages * 50.0  # Stage 1 = 50% of overall
                    self.system_monitor.update_stage_progress(page_num, overall_pct)

                # Save to intermediate cache (already in correct format)
                self.intermediate_cache.save_ocr_result(page_num, ocr_result)

                # Emit OCR result to SSE clients
                if self.result_emitter and self.job_id:
                    # Extract actual model from metadata
                    actual_model = ocr_result.metadata.get("model", stage_config["model_name"])
                    self.result_emitter.emit_ocr_page(self.job_id, page_number, ocr_text, model=actual_model)

                # Log page completion with BAML OCR metrics
                if self.system_monitor:
                    page_metadata = ocr_result.metadata.copy() if ocr_result.metadata else {}
                    page_metadata['text'] = ocr_text

                    self.system_monitor.log_page_completion(
                        page_number=page_number,
                        stage="ocr",
                        page_duration=page_time,
                        page_metadata=page_metadata
                    )

                if self.verbose:
                    print(f"  Page {page_number}: {ocr_text[:50]}... ({page_time:.2f}s)")

            # Save checkpoint after batch (not after each page)
            stage_metadata = {
                'model_used': stage_config["model_name"],
                'resolution_mode': stage_config.get("resolution_mode"),
                'crop_mode': stage_config.get("crop_mode"),
                'batch_mode': True,
                'batch_size': self.page_batch_size
            }
            self.checkpoint_manager.save_stage_progress(
                stage_name="ocr",
                last_completed_page=batch_end - 1,
                total_pages=total_pages,
                stage_metadata=stage_metadata
            )

            # Emit progress after batch (OCR is 60% of total)
            ocr_progress = (batch_end / total_pages) * 60.0
            self._emit_progress(ocr_progress, batch_end, "ocr")

        stage_time = time.time() - stage_start

        # Log stage transition
        if self.system_monitor:
            self.system_monitor.log_stage_transition(
                from_stage="ocr",
                to_stage="merge",
                transition_metadata={'stage1_duration': stage_time}
            )

        return StageResult(
            stage_name="ocr",
            pages_processed=total_pages - start_page,
            total_time=stage_time,
            model_used=stage_config["model_name"],
            strategy_used=stage_config["strategy_type"],
            avg_page_time=stage_time / (total_pages - start_page)
        )

    def _stream_merge_with_retry(
        self,
        image: Image.Image,
        embedded_text: str,
        ocr_text: str,
        page_num: int,
        max_retries: int = 3
    ) -> str:
        """
        Stream merge text with OOM retry logic.

        Progressively reduces image resolution on OOM errors.
        Emits chunks via result_emitter during streaming.

        Args:
            image: PIL Image to process
            embedded_text: Text embedded in PDF
            ocr_text: Text extracted via OCR
            page_num: Page number (for logging and events)
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            Complete merged text (accumulated from chunks)

        Raises:
            RuntimeError: If merge fails after all retry attempts
            Exception: If non-OOM error occurs
        """
        resolution_steps = [1024, 768, 512]
        accumulated_text = ""

        # Phase 4: Initialize SnapshotAccumulator for throttled database writes
        accumulator = SnapshotAccumulator(throttle_ms=100, throttle_tokens=50)

        for attempt in range(max_retries):
            try:
                # Adjust resolution for retry attempts
                current_max_dim = resolution_steps[min(attempt, len(resolution_steps) - 1)]
                if attempt > 0:
                    logger.warning(
                        f"OOM retry attempt {attempt + 1}/{max_retries}, "
                        f"reducing resolution to {current_max_dim}px for page {page_num}"
                    )
                    image = resize_image_for_merge(image, max_dimension=current_max_dim)

                # Phase 4 + BAML: Stream chunks from BAML client
                baml_image = pil_to_baml_image(image)

                # Iterate BAML stream properly using async for
                async def _consume_baml_stream():
                    """Consume BAML stream and accumulate text."""
                    accumulated = ""
                    baml_stream = b.stream.MergeTextsStreaming(
                        page_image=baml_image,
                        embedded_text=embedded_text,
                        ocr_text=ocr_text
                    )

                    # BAML streams implement __aiter__, use async for
                    async for chunk in baml_stream:
                        accumulated += chunk

                        # Phase 4: Throttled snapshot writes (returns snapshot if threshold met)
                        if self.streaming_repository and self.job_id:
                            try:
                                from uuid import UUID
                                snapshot = accumulator.add_chunk(chunk, is_final=False)

                                if snapshot:
                                    # Write throttled snapshot to database
                                    await self.streaming_repository.write_snapshot(
                                        job_id=UUID(self.job_id),
                                        page_num=page_num,
                                        snapshot_text=snapshot,
                                        stage='merge',
                                        is_final=False
                                    )
                            except Exception as e:
                                logger.warning(f"Failed to write streaming snapshot: {e}")
                                # Continue processing even if streaming fails

                        # Legacy SSE emission (deprecated, will be removed in Phase 5)
                        if self.result_emitter and self.job_id:
                            self.result_emitter.emit_merge_chunk(
                                job_id=self.job_id,
                                page_num=page_num,
                                chunk=chunk,
                                is_final=False
                            )

                    return accumulated

                # Run the async stream consumption in the event loop thread
                accumulated_text = run_async_in_thread(_consume_baml_stream(), self._event_loop)

                # Phase 4: Final flush and mark complete
                if self.streaming_repository and self.job_id:
                    try:
                        from uuid import UUID
                        final_snapshot = accumulator.flush()
                        run_async_in_thread(
                            self.streaming_repository.mark_complete(
                                job_id=UUID(self.job_id),
                                page_num=page_num,
                                final_text=final_snapshot
                            ),
                            self._event_loop
                        )
                    except Exception as e:
                        logger.warning(f"Failed to mark stream complete: {e}")

                # Legacy SSE final chunk marker (deprecated)
                if self.result_emitter and self.job_id:
                    self.result_emitter.emit_merge_chunk(
                        job_id=self.job_id,
                        page_num=page_num,
                        chunk="",
                        is_final=True
                    )

                # Success - log and return
                if attempt > 0:
                    logger.info(
                        f"Streaming merge succeeded on retry attempt {attempt + 1} "
                        f"with resolution {current_max_dim}px for page {page_num}"
                    )

                return accumulated_text

            except Exception as e:
                # Phase 4: Mark stream as failed on error
                if self.streaming_repository and self.job_id:
                    try:
                        from uuid import UUID
                        run_async_in_thread(
                            self.streaming_repository.mark_failed(
                                job_id=UUID(self.job_id),
                                page_num=page_num,
                                error={"message": str(e), "attempt": attempt + 1}
                            ),
                            self._event_loop
                        )
                    except Exception as mark_err:
                        logger.warning(f"Failed to mark stream as failed: {mark_err}")

                # Check if this is an OOM error based on error message
                error_msg = str(e).lower()
                is_oom_error = (
                    "out of memory" in error_msg or
                    "cuda" in error_msg or
                    "oom" in error_msg
                )

                if is_oom_error and attempt < max_retries - 1:
                    logger.warning(
                        f"CUDA OOM detected on page {page_num} attempt {attempt + 1}, "
                        f"retrying with lower resolution..."
                    )
                    # Reset accumulator for retry
                    accumulator.reset()
                    continue
                else:
                    # Not OOM or final attempt failed - re-raise
                    logger.error(f"Streaming merge failed on page {page_num} attempt {attempt + 1}: {e}")
                    raise

        # Should not reach here, but for safety
        raise RuntimeError(f"Failed to merge page {page_num} after {max_retries} attempts")

    def _run_merge_stage(
        self,
        pages_data: List,
        stage_config: Dict[str, Any],
        output_path: Path,
        output_format: str,
        dpi: int,
        resume: bool
    ) -> StageResult:
        """
        Run Stage 2: Merge OCR with embedded text for all pages.

        Args:
            pages_data: List of (embedded_text, image, has_text) tuples
            stage_config: Validated configuration for merge stage
            output_path: Path to output file
            output_format: Output format
            dpi: DPI setting
            resume: Whether to resume from checkpoint

        Returns:
            StageResult with stage metrics
        """
        # Container mode: HTTP client already initialized
        if self.system_monitor:
            self.system_monitor.set_model_info(
                model_type=stage_config["model_name"],
                model_id="container",
                device_map=None
            )

        # Update system monitor
        if self.system_monitor:
            self.system_monitor.set_active_stage(
                stage_name="merge",
                stage_total_pages=len(pages_data),
                loaded_models=[stage_config["model_name"]]
            )

        # Determine start page
        start_page = 0
        if resume:
            start_page = self.checkpoint_manager.get_stage_resume_page("merge")
            if self.verbose and start_page > 0:
                print(f"[Resume] Starting from page {start_page + 1}")

        total_pages = len(pages_data)
        stage_start = time.time()

        # Phase 3.7A: Initialize buffers for output and page results
        output_buffer = []  # Buffer for output file writes
        page_results_buffer = []  # Buffer for DB page results
        pages_since_last_checkpoint = 0  # Track pages for adaptive checkpointing

        # Process each page
        for idx in range(start_page, total_pages):
            embedded_text, image, has_text = pages_data[idx]
            page_num = idx + 1
            page_start = time.time()

            # Update page timing in monitor
            if self.system_monitor:
                self.system_monitor.update_page_timing(page_start)

            if self.verbose:
                progress_pct = ((idx + 1) / total_pages) * 100
                print(f"[Merge] Page {page_num}/{total_pages} ({progress_pct:.1f}%)...", end=" ", flush=True)

            # Update monitor
            if self.system_monitor:
                overall_pct = 50.0 + (idx + 1) / total_pages * 50.0  # Stage 2 = 50-100%
                self.system_monitor.update_stage_progress(idx, overall_pct)

            # Load OCR result from cache
            ocr_result = self.intermediate_cache.load_ocr_result(idx)
            if not ocr_result:
                raise RuntimeError(f"Missing OCR result for page {idx}")

            # Run merge with container
            page_start = time.time()

            # Build merge prompt with embedded and OCR text
            merge_prompt_template = self.custom_prompts.get("merge") if self.custom_prompts else None
            if not merge_prompt_template:
                # Use default merge prompt
                merge_prompt = f"""Compare and merge these two text versions from the same document page:

Embedded Text (from PDF):
{embedded_text or ""}

OCR Text (from image):
{ocr_result.ocr_text}

Provide the most accurate merged version by combining both sources, fixing any OCR errors, and preserving layout. Return only the final text."""
            else:
                merge_prompt = merge_prompt_template.format(
                    embedded_text=embedded_text or "",
                    ocr_text=ocr_result.ocr_text
                )

            # Resize image before merge to prevent CUDA OOM in Qwen3-VL
            # Large legal-size PDFs (2481x3508 @ 300 DPI) exceed Qwen's GPU memory
            merge_image = resize_image_for_merge(image, max_dimension=1024)

            # Emit inference start event and system message for UI
            page_start = time.time()
            if self.result_emitter:
                self.result_emitter.emit_inference_start(self.job_id, idx, "merge")
                self.result_emitter.emit_system_message(
                    self.job_id,
                    f"Starting merge inference for page {idx}...",
                    {"page": idx, "stage": "merge"}
                )

            # Call merge model with feature flag for streaming vs non-streaming
            # Check feature flag for streaming
            from config.settings import get_settings
            settings = get_settings()

            if settings.enable_merge_streaming and self.baml_ocr_service:
                # Phase 4: Initialize stream row before merge processing
                if self.streaming_repository and self.job_id:
                    try:
                        from uuid import UUID
                        run_async_in_thread(
                            self.streaming_repository.create_stream(
                                job_id=UUID(self.job_id),
                                page_num=page_num,
                                stage='merge'
                            ),
                            self._event_loop
                        )
                    except Exception as e:
                        logger.warning(f"Failed to initialize stream for page {page_num}: {e}")

                # Use streaming merge with OOM retry logic
                merged_text = self._stream_merge_with_retry(
                    image=merge_image,
                    embedded_text=embedded_text or "",
                    ocr_text=ocr_result.ocr_text,
                    page_num=page_num
                )
                # Create mock result object with metadata for downstream compatibility
                merge_model_result = type('StreamingResult', (object,), {
                    'text': merged_text,
                    'metadata': {'streaming': True, 'actual_model': stage_config["model_name"]}
                })()
            else:
                # Use non-streaming merge (fallback or feature disabled)
                # Use BAML service if available (type-safe operations with intelligent merging)
                merge_model_result = None
                max_retries = 3
                resolution_steps = [1024, 768, 512]  # Progressive reduction

                for attempt in range(max_retries):
                    try:
                        # Adjust resolution for retry attempts
                        current_max_dim = resolution_steps[min(attempt, len(resolution_steps) - 1)]
                        if attempt > 0:
                            logger.warning(f"OOM retry attempt {attempt + 1}/{max_retries}, reducing resolution to {current_max_dim}px")
                            merge_image = resize_image_for_merge(image, max_dimension=current_max_dim)

                        # Phase 4 + BAML: Use BAML client for non-streaming merge fallback
                        baml_image = pil_to_baml_image(merge_image)
                        merged_text = run_async_in_thread(
                            b.MergeTexts(
                                page_image=baml_image,
                                embedded_text=embedded_text or "",
                                ocr_text=ocr_result.ocr_text,
                                custom_prompt=self.custom_prompts.get("merge") if self.custom_prompts else None
                            ),
                            event_loop=self._event_loop
                        )

                        # BAML now returns string directly
                        merge_model_result = OCRPageResult(
                            page_num=page_num,
                            ocr_text=merged_text or "",
                            method="merge",
                            processing_time=0.0,  # BAML doesn't provide timing
                            metadata={'via_baml': True, 'streaming': False}
                        )

                        # Success - break out of retry loop
                        if attempt > 0:
                            logger.info(f"Merge succeeded on retry attempt {attempt + 1} with resolution {current_max_dim}px")
                        break

                    except Exception as e:
                        error_msg = str(e).lower()
                        is_oom_error = "out of memory" in error_msg or "cuda" in error_msg or "oom" in error_msg

                        if is_oom_error and attempt < max_retries - 1:
                            logger.warning(f"CUDA OOM detected on attempt {attempt + 1}, retrying with lower resolution...")
                            continue
                        else:
                            # Not OOM or final attempt failed - re-raise
                            logger.error(f"Merge failed on attempt {attempt + 1}: {e}")
                            raise

                if merge_model_result is None:
                    raise RuntimeError("Merge model inference failed after all retry attempts")

                merged_text = merge_model_result.text or ""
            page_time = time.time() - page_start

            # Emit inference complete event and system message for UI
            if self.result_emitter:
                self.result_emitter.emit_inference_complete(self.job_id, idx, "merge", page_time)
                self.result_emitter.emit_system_message(
                    self.job_id,
                    f"Completed merge for page {idx} in {page_time:.2f}s",
                    {"page": idx, "stage": "merge", "duration": page_time}
                )

            # Phase 3.7A: Buffer output instead of writing immediately
            output_buffer.append((page_num, merged_text, page_time, "merge"))

            # Phase 3.7A: Buffer page result for bulk DB insert
            if self.job_repository and self.job_id:
                page_results_buffer.append({
                    "page_num": page_num,
                    "merge_text": merged_text,
                    "merge_processing_time": page_time
                })

            # Phase 3.7A: Flush buffers every OUTPUT_BUFFER_SIZE pages
            if len(output_buffer) >= self.OUTPUT_BUFFER_SIZE:
                # Flush output buffer
                run_async_in_thread(
                    self._flush_output_buffer(
                        output_path=output_path,
                        output_buffer=output_buffer,
                        append=(idx > 0 or start_page > 0 or len(output_buffer) > 0)
                    ),
                    self._event_loop
                )
                output_buffer.clear()

                # Flush page results buffer
                if page_results_buffer:
                    run_async_in_thread(
                        self._flush_page_results_buffer(
                            job_id=self.job_id,
                            page_results_buffer=page_results_buffer
                        ),
                        self._event_loop
                    )
                    page_results_buffer.clear()

            # Emit merged result to SSE clients with metadata
            if self.result_emitter and self.job_id:
                # Extract actual model from merge result metadata
                actual_model = merge_model_result.metadata.get("actual_model", stage_config["model_name"])
                # Check if streaming was used
                streaming_complete = merge_model_result.metadata.get("streaming", False)
                self.result_emitter.emit_merge_page(
                    job_id=self.job_id,
                    page_num=page_num,
                    text=merged_text,
                    processing_time=page_time,
                    total_pages=total_pages,
                    model=actual_model,
                    streaming_complete=streaming_complete
                )

            # Phase 3.7A: Adaptive checkpointing - only save if conditions are met
            pages_since_last_checkpoint += 1
            if self.checkpoint_manager.should_save_checkpoint(pages_since_last_checkpoint):
                stage_metadata = {
                    'model_used': stage_config["model_name"]
                }
                self.checkpoint_manager.save_stage_progress(
                    stage_name="merge",
                    last_completed_page=idx,
                    total_pages=total_pages,
                    stage_metadata=stage_metadata
                )
                pages_since_last_checkpoint = 0  # Reset counter

            # Emit progress (merge is 60-90% of total)
            merge_progress = 60.0 + ((idx + 1) / total_pages) * 30.0
            # BUG FIX: Pass actual pages completed (idx + 1), not total_pages
            # This was causing pages_completed to jump to total_pages on first merge page
            self._emit_progress(merge_progress, (idx + 1), "merge")

            # Log page completion for merge stage
            if self.system_monitor:
                page_metadata = {
                    'text': merged_text,
                    'embedded_text_length': len(embedded_text or ""),
                    'ocr_text_length': len(ocr_result.ocr_text)
                }
                # Add metadata from model result if available
                if hasattr(merge_model_result, 'metadata') and merge_model_result.metadata:
                    page_metadata.update(merge_model_result.metadata)

                self.system_monitor.log_page_completion(
                    page_number=page_num,
                    stage="merge",
                    page_duration=page_time,
                    page_metadata=page_metadata
                )

            if self.verbose:
                print(f"({page_time:.2f}s)", flush=True)

        # Phase 3.7A: Flush remaining buffered pages at end of stage
        if output_buffer:
            run_async_in_thread(
                self._flush_output_buffer(
                    output_path=output_path,
                    output_buffer=output_buffer,
                    append=True
                ),
                self._event_loop
            )
            output_buffer.clear()

        if page_results_buffer:
            run_async_in_thread(
                self._flush_page_results_buffer(
                    job_id=self.job_id,
                    page_results_buffer=page_results_buffer
                ),
                self._event_loop
            )
            page_results_buffer.clear()

        stage_time = time.time() - stage_start

        # Log completion
        if self.system_monitor:
            self.system_monitor.log_stage_transition(
                from_stage="merge",
                to_stage="completed",
                transition_metadata={'stage2_duration': stage_time}
            )

        return StageResult(
            stage_name="merge",
            pages_processed=total_pages - start_page,
            total_time=stage_time,
            model_used=stage_config["model_name"],
            strategy_used=stage_config["strategy_type"],
            avg_page_time=stage_time / (total_pages - start_page)
        )

    def _write_page_result(
        self,
        output_path: Path,
        page_num: int,
        text: str,
        processing_time: float,
        method: str,
        append: bool
    ) -> None:
        """Write page result to output file."""
        mode = 'a' if append else 'w'

        metadata = (
            f"<!-- Page {page_num} | "
            f"Method: {method.upper()} | "
            f"Time: {processing_time:.2f}s | "
            f"Chars: {len(text)} -->\n"
        )

        with open(output_path, mode, encoding='utf-8') as f:
            f.write(metadata)
            f.write(text)
            f.write("\n\n")
            f.flush()

    async def _flush_output_buffer(
        self,
        output_path: Path,
        output_buffer: List[tuple],
        append: bool = True
    ) -> None:
        """
        Flush buffered pages to output file (Phase 3.7A).

        Args:
            output_path: Path to output file
            output_buffer: List of (page_num, text, processing_time, method) tuples
            append: Whether to append or overwrite
        """
        if not output_buffer:
            return

        mode = 'a' if append else 'w'

        with open(output_path, mode, encoding='utf-8') as f:
            for page_num, text, processing_time, method in output_buffer:
                metadata = (
                    f"<!-- Page {page_num} | "
                    f"Method: {method.upper()} | "
                    f"Time: {processing_time:.2f}s | "
                    f"Chars: {len(text)} -->\n"
                )
                f.write(metadata)
                f.write(text)
                f.write("\n\n")
            f.flush()

        logger.debug(f"Flushed {len(output_buffer)} pages to {output_path}")

    async def _flush_page_results_buffer(
        self,
        job_id: str,
        page_results_buffer: List[Dict[str, Any]]
    ) -> None:
        """
        Flush buffered page results to database (Phase 3.7A).

        Args:
            job_id: Job ID (UUID as string)
            page_results_buffer: List of page result dicts
        """
        if not page_results_buffer or not self.job_repository:
            return

        try:
            from uuid import UUID
            await self.job_repository.bulk_create_page_results(
                job_id=UUID(job_id),
                page_results=page_results_buffer
            )
            logger.debug(f"Bulk inserted {len(page_results_buffer)} page results for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to bulk insert page results: {e}")
            # Fall back to individual inserts
            for page_result in page_results_buffer:
                try:
                    await self.job_repository.create_page_result(
                        job_id=UUID(job_id),
                        **page_result
                    )
                except Exception as inner_e:
                    logger.error(f"Failed to insert page result: {inner_e}")
