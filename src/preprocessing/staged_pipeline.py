"""Staged pipeline processor for eliminating model-switching fragmentation."""
from typing import List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
import time
import logging
import torch

from .pdf_handler import PDFHandler
from .checkpoint_manager import CheckpointManager
from .intermediate_cache import IntermediateCache, OCRPageResult
from ..models.gpu_strategy_manager import GPUStrategyManager
from ..utils.system_monitor import SystemMonitor
from ..utils.memory_profiler import MemoryProfiler

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        model_manager,
        pdf_handler: PDFHandler,
        verbose: bool = False,
        enable_memory_profiling: bool = False,
        enable_system_monitoring: bool = True,
        monitor_interval: int = 30,
        prefer_quality: bool = True,
        progress_callback: Optional[Any] = None
    ):
        """
        Initialize staged pipeline processor.

        Args:
            model_manager: ModelManager instance
            pdf_handler: PDFHandler instance
            verbose: Print progress messages
            enable_memory_profiling: Enable memory profiling
            enable_system_monitoring: Enable system resource monitoring
            monitor_interval: Monitoring interval in seconds
            prefer_quality: Prefer quality over speed
            progress_callback: Optional callback function(progress_pct, pages_completed, stage)
        """
        self.model_manager = model_manager
        self.pdf_handler = pdf_handler
        self.verbose = verbose
        self.enable_memory_profiling = enable_memory_profiling
        self.enable_system_monitoring = enable_system_monitoring
        self.monitor_interval = monitor_interval
        self.prefer_quality = prefer_quality
        self.progress_callback = progress_callback

        # Will be initialized in process_pdf()
        self.gpu_strategy_manager = None
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

        # Initialize GPU strategy manager
        self.gpu_strategy_manager = GPUStrategyManager(
            self.model_manager,
            strategy_preference="auto",
            verbose=self.verbose,
            enable_inference_profiling=self.enable_memory_profiling
        )

        # Run preflight validation for all stages
        if self.verbose:
            print("\n[Preflight Validation] Testing configurations for all stages...")

        try:
            stage_configs = self.gpu_strategy_manager.run_staged_pipeline_preflight(
                dpi=dpi,
                prefer_quality=self.prefer_quality
            )
        except RuntimeError as e:
            if self.verbose:
                print(f"\n[Preflight Failed] {e}")
            raise

        if self.verbose:
            print("\n[Preflight Complete] Validated configurations:")
            for stage_name, config in stage_configs.items():
                print(f"  {stage_name.upper()}: {config['model_name']} on {config['strategy_type']}")
                print(f"    Quality: {config['quality_score']:.1f}, Peak: {config['actual_peak_gb']:.2f}GB")

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

            # Clear checkpoint and cache on success
            self.checkpoint_manager.clear()
            self.intermediate_cache.clear()

            # Emit final completion (100%)
            self._emit_progress(100.0, total_pages, "complete")

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

        finally:
            # Cleanup
            if self.system_monitor:
                self.system_monitor.stop()
            if self.gpu_strategy_manager:
                self.gpu_strategy_manager.cleanup()

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
        # Initialize GPU strategy for OCR stage
        self.gpu_strategy_manager.initialize_for_stage_processing(
            stage_name="ocr",
            model_name=stage_config["model_name"],
            dpi=dpi,
            deepseek_resolution_mode=stage_config.get("resolution_mode"),
            disable_crop_mode=not stage_config.get("crop_mode", True),
            prefer_quality=self.prefer_quality,
            use_validation_based_selection=False  # Already validated
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

        # Get model for OCR
        model = self.gpu_strategy_manager.get_model_for_task("ocr")

        # Set model info in system monitor
        if self.system_monitor:
            model_id = getattr(model, 'model_id', 'unknown')
            device_map = getattr(model.model, 'hf_device_map', None) if hasattr(model, 'model') else None
            self.system_monitor.set_model_info(
                model_type=stage_config["model_name"],
                model_id=model_id,
                device_map=device_map
            )

        # Get primary device for health checks
        primary_device = self.gpu_strategy_manager.get_primary_device()

        # Process each page
        for idx in range(start_page, total_pages):
            embedded_text, image, has_text = pages_data[idx]
            page_num = idx + 1
            page_start = time.time()

            # Update page timing in monitor
            if self.system_monitor:
                self.system_monitor.update_page_timing(page_start)

            # Per-page GPU health check
            self._check_gpu_health_before_page(
                device_id=primary_device,
                required_gb=stage_config['actual_peak_gb'],
                page_num=page_num,
                stage_name="ocr"
            )

            # Optional: Log detailed memory snapshot
            if self.enable_memory_profiling:
                self._log_page_memory(primary_device, page_num, "ocr")

            if self.verbose:
                progress_pct = ((idx + 1) / total_pages) * 100
                print(f"[OCR] Page {page_num}/{total_pages} ({progress_pct:.1f}%)...", end=" ", flush=True)

            # Update monitor
            if self.system_monitor:
                overall_pct = (idx + 1) / total_pages * 50.0  # Stage 1 = 50% of overall
                self.system_monitor.update_stage_progress(idx, overall_pct)

            # Run OCR
            page_start = time.time()
            ocr_model_result = model.process_image(image, prompt_type="ocr", prompts=self.custom_prompts)
            ocr_text = ocr_model_result.text or ""
            page_time = time.time() - page_start

            # Save to intermediate cache
            ocr_result = OCRPageResult(
                page_num=idx,
                ocr_text=ocr_text,
                method="ocr",
                processing_time=page_time,
                metadata={
                    'model': stage_config["model_name"],
                    'resolution_mode': stage_config.get("resolution_mode"),
                    'crop_mode': stage_config.get("crop_mode")
                }
            )
            self.intermediate_cache.save_ocr_result(idx, ocr_result)

            # Save checkpoint
            stage_metadata = {
                'model_used': stage_config["model_name"],
                'resolution_mode': stage_config.get("resolution_mode"),
                'crop_mode': stage_config.get("crop_mode")
            }
            self.checkpoint_manager.save_stage_progress(
                stage_name="ocr",
                last_completed_page=idx,
                total_pages=total_pages,
                stage_metadata=stage_metadata
            )

            # Emit progress (OCR is 60% of total)
            ocr_progress = ((idx + 1) / total_pages) * 60.0
            self._emit_progress(ocr_progress, idx + 1, "ocr")

            # Log page completion with DeepSeek OCR metrics
            if self.system_monitor:
                page_metadata = {
                    'text': ocr_text,
                    'resolution_mode': stage_config.get("resolution_mode"),
                    'crop_mode': stage_config.get("crop_mode")
                }
                # Add metadata from model result if available
                if hasattr(ocr_model_result, 'metadata') and ocr_model_result.metadata:
                    page_metadata.update(ocr_model_result.metadata)

                self.system_monitor.log_page_completion(
                    page_number=page_num,
                    stage="ocr",
                    page_duration=page_time,
                    page_metadata=page_metadata
                )

            if self.verbose:
                print(f"({page_time:.2f}s)", flush=True)

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
        # Unload OCR model first (if loaded)
        if self.model_manager.current_model_name:
            self.model_manager.unload_model(self.model_manager.current_model_name)

        # Initialize GPU strategy for merge stage
        self.gpu_strategy_manager.initialize_for_stage_processing(
            stage_name="merge",
            model_name=stage_config["model_name"],
            dpi=dpi,
            prefer_quality=self.prefer_quality,
            use_validation_based_selection=False  # Already validated
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

        # Get model for merge
        model = self.gpu_strategy_manager.get_model_for_task("merge")

        # Set model info in system monitor
        if self.system_monitor:
            model_id = getattr(model, 'model_id', 'unknown')
            device_map = getattr(model.model, 'hf_device_map', None) if hasattr(model, 'model') else None
            self.system_monitor.set_model_info(
                model_type=stage_config["model_name"],
                model_id=model_id,
                device_map=device_map
            )

        # Get primary device for health checks
        primary_device = self.gpu_strategy_manager.get_primary_device()

        # Process each page
        for idx in range(start_page, total_pages):
            embedded_text, image, has_text = pages_data[idx]
            page_num = idx + 1
            page_start = time.time()

            # Update page timing in monitor
            if self.system_monitor:
                self.system_monitor.update_page_timing(page_start)

            # Per-page GPU health check
            self._check_gpu_health_before_page(
                device_id=primary_device,
                required_gb=stage_config['actual_peak_gb'],
                page_num=page_num,
                stage_name="merge"
            )

            # Optional: Log detailed memory snapshot
            if self.enable_memory_profiling:
                self._log_page_memory(primary_device, page_num, "merge")

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

            # Run merge
            page_start = time.time()
            merge_model_result = model.merge_texts(
                image=image,
                embedded_text=embedded_text or "",
                ocr_text=ocr_result.ocr_text,
                prompts=self.custom_prompts
            )
            merged_text = merge_model_result.text or ""
            page_time = time.time() - page_start

            # Write to output file (append mode)
            self._write_page_result(
                output_path=output_path,
                page_num=page_num,
                text=merged_text,
                processing_time=page_time,
                method="merge",
                append=(idx > 0 or start_page > 0)
            )

            # Save checkpoint
            stage_metadata = {
                'model_used': stage_config["model_name"]
            }
            self.checkpoint_manager.save_stage_progress(
                stage_name="merge",
                last_completed_page=idx,
                total_pages=total_pages,
                stage_metadata=stage_metadata
            )

            # Emit progress (merge is 60-90% of total)
            merge_progress = 60.0 + ((idx + 1) / total_pages) * 30.0
            self._emit_progress(merge_progress, total_pages, "merge")

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

    def _check_gpu_health_before_page(
        self,
        device_id: int,
        required_gb: float,
        page_num: int,
        stage_name: str
    ) -> None:
        """
        Check if GPU has sufficient memory for next page.

        Args:
            device_id: GPU device ID to check
            required_gb: Required VRAM in GB (from validation)
            page_num: Current page number (for logging)
            stage_name: Current stage name (for logging)

        Raises:
            RuntimeError: If insufficient VRAM after cleanup attempt
        """
        # Get current GPU state
        self.gpu_strategy_manager.analyzer._detect_gpus()
        gpu = self.gpu_strategy_manager.analyzer.gpus[device_id]

        # Safety buffer (2GB recommended)
        safety_buffer_gb = 2.0
        available_gb = gpu.free_memory_gb - safety_buffer_gb

        if available_gb < required_gb:
            # Log warning
            if self.verbose:
                print(f"\n⚠️  Low VRAM before page {page_num} ({stage_name})")
                print(f"   Available: {available_gb:.2f}GB (after {safety_buffer_gb}GB buffer)")
                print(f"   Required: {required_gb:.2f}GB")
                print(f"   Attempting cleanup...")

            logger.warning(
                f"Low VRAM before page {page_num}: "
                f"available={available_gb:.2f}GB, required={required_gb:.2f}GB"
            )

            # Try cleanup
            torch.cuda.empty_cache()
            torch.cuda.synchronize(device_id)

            # Recheck after cleanup
            self.gpu_strategy_manager.analyzer._detect_gpus()
            gpu = self.gpu_strategy_manager.analyzer.gpus[device_id]
            available_gb = gpu.free_memory_gb - safety_buffer_gb

            if available_gb < required_gb:
                # Still insufficient after cleanup
                error_msg = (
                    f"Insufficient VRAM for page {page_num} after cleanup: "
                    f"Available: {available_gb:.2f}GB, Required: {required_gb:.2f}GB"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                # Cleanup successful
                if self.verbose:
                    print(f"   ✓ Cleanup successful! Now have {available_gb:.2f}GB available")
                logger.info(f"Cleanup successful: now have {available_gb:.2f}GB available")

    def _log_page_memory(
        self,
        device_id: int,
        page_num: int,
        stage_name: str
    ) -> None:
        """
        Log detailed memory snapshot for this page.

        Args:
            device_id: GPU device ID
            page_num: Current page number
            stage_name: Current stage name
        """
        if not self.system_monitor:
            return

        # Capture memory snapshot
        snapshot = MemoryProfiler.capture_snapshot(device_id)

        # Log to system monitor
        from datetime import datetime
        self.system_monitor._write_metrics({
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'event_type': 'page_memory_check',
            'page': page_num,
            'stage': stage_name,
            'gpu_id': device_id,
            'allocated_gb': snapshot.allocated_gb,
            'free_gb': snapshot.free_gb,
            'peak_gb': snapshot.peak_gb,
            'reserved_gb': snapshot.reserved_gb
        })

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
