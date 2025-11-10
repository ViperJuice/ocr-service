"""Hybrid PDF processing pipeline."""
from typing import List, Optional, Literal, Callable, Tuple
from pathlib import Path
from dataclasses import dataclass
import time
import gc
import torch
import logging

from .pdf_handler import PDFHandler
from .spatial_data import PageStructure
from .spatial_prompts import SpatialPromptBuilder
from .image_annotator import ImageAnnotator
from .checkpoint_manager import CheckpointManager
from ..utils.system_monitor import SystemMonitor

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """Result for a single PDF page."""
    page_num: int
    text: str
    method: Literal["embedded", "ocr", "hybrid"]
    processing_time: float
    metadata: dict
    output_format: str = "text"


class HybridPDFProcessor:
    """Process PDFs with intelligent hybrid text extraction."""
    
    def __init__(
        self,
        model_manager,
        pdf_handler: PDFHandler,
        method: Literal["auto", "extract", "ocr", "hybrid"] = "auto",
        force_ocr: bool = False,
        min_text_chars: int = 10,
        verbose: bool = False,
        output_format: str = "text",
        document_context: Optional[str] = None,
        enable_memory_optimization: bool = True,
        enable_incremental_mode: bool = False,
        enable_oom_recovery: bool = True,
        enable_spatial_hints: bool = True,
        enable_bbox_annotations: bool = False,
        gpu_strategy: Literal["auto", "dual", "sequential", "sharded"] = "auto",
        disable_crop_mode: bool = False,
        enable_memory_profiling: bool = False,
        enable_validation: bool = False,
        merge_model_preference: Optional[str] = None,
        prefer_quality: bool = True,
        enable_checkpointing: bool = True,
        enable_system_monitoring: bool = True,
        monitor_interval: int = 30,
    ):
        """
        Initialize hybrid PDF processor.
        
        Args:
            model_manager: ModelManager instance with loaded model
            pdf_handler: PDFHandler instance for extraction
            method: Processing method (auto, extract, ocr, hybrid)
            force_ocr: Force OCR even if embedded text exists
            min_text_chars: Minimum characters to consider page as having text
            verbose: Print detailed processing information
            output_format: Output format (text, markdown, json)
            document_context: Optional document context/description
            enable_memory_optimization: Enable GPU cache clearing between passes
            enable_incremental_mode: Unload/reload model between steps (slowest, least memory)
            enable_oom_recovery: Enable automatic image resizing on OOM errors
            enable_spatial_hints: Enable spatial hint extraction (Phase 1)
            enable_bbox_annotations: Draw bounding boxes on images (Phase 2)
            gpu_strategy: GPU loading strategy (auto, dual, sequential, sharded)
            disable_crop_mode: Disable crop mode in DeepSeek
            enable_memory_profiling: Enable dynamic memory profiling
            enable_validation: Enable extraction validation with optional refinement
            merge_model_preference: Preferred merge model (None=auto, "qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b")
            prefer_quality: Prefer quality over speed when auto-selecting models
            enable_checkpointing: Enable checkpoint/resume functionality (default: True)
            enable_system_monitoring: Enable system resource monitoring (default: True)
            monitor_interval: System monitoring interval in seconds (default: 30)
        """
        self.model_manager = model_manager
        self.pdf_handler = pdf_handler
        self.method = method
        self.force_ocr = force_ocr
        self.min_text_chars = min_text_chars
        self.verbose = verbose
        self.output_format = output_format
        self.document_context = document_context
        self.enable_memory_optimization = enable_memory_optimization
        self.enable_incremental_mode = enable_incremental_mode
        self.enable_oom_recovery = enable_oom_recovery
        self.enable_spatial_hints = enable_spatial_hints
        self.enable_bbox_annotations = enable_bbox_annotations
        self.gpu_strategy = gpu_strategy
        self.disable_crop_mode = disable_crop_mode
        self.enable_memory_profiling = enable_memory_profiling
        self.enable_validation = enable_validation
        self.merge_model_preference = merge_model_preference
        self.prefer_quality = prefer_quality
        self.enable_checkpointing = enable_checkpointing
        self.enable_system_monitoring = enable_system_monitoring
        self.monitor_interval = monitor_interval

        # Initialize spatial processing components
        self.spatial_prompt_builder = SpatialPromptBuilder() if enable_spatial_hints else None
        self.image_annotator = ImageAnnotator() if enable_bbox_annotations else None

        # GPU strategy manager (lazy initialization in process_pdf)
        self.gpu_strategy_manager = None
    
    def process_pdf(
        self,
        pdf_path: Path,
        max_pages: Optional[int] = None,
        dpi: int = 300,
        output_path: Optional[Path] = None,
        resume: bool = True
    ) -> List[PageResult]:
        """
        Process PDF with hybrid approach.

        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum number of pages to process
            dpi: DPI for image extraction
            output_path: Path to output file (required for checkpointing)
            resume: Whether to resume from checkpoint if exists (default: True)

        Returns:
            List of PageResult objects
        """
        # Initialize GPU strategy if hybrid mode
        if self.method in ["auto", "hybrid"] and not self.enable_incremental_mode:
            from ..models.gpu_strategy_manager import GPUStrategyManager
            self.gpu_strategy_manager = GPUStrategyManager(
                self.model_manager,
                strategy_preference=self.gpu_strategy,
                verbose=self.verbose,
                enable_inference_profiling=self.enable_memory_profiling
            )
            # Pass DPI, profiling settings, and model preferences
            self.gpu_strategy_manager.initialize_for_hybrid_processing(
                ocr_model_name="deepseek-ocr",
                merge_model_name=self.merge_model_preference,
                dpi=dpi,
                enable_profiling=self.enable_memory_profiling,
                disable_crop_mode=self.disable_crop_mode,
                prefer_quality=self.prefer_quality
            )

        # Initialize checkpoint manager
        checkpoint_manager = None
        start_page = 0
        if self.enable_checkpointing and output_path:
            processing_params = {
                'dpi': dpi,
                'method': self.method,
                'format': self.output_format,
                'force_ocr': self.force_ocr,
                'merge_model': self.merge_model_preference,
            }
            checkpoint_manager = CheckpointManager(output_path, pdf_path, processing_params)

            # Check for existing checkpoint
            if resume:
                start_page = checkpoint_manager.get_resume_page()
                if start_page > 0:
                    if self.verbose:
                        print(f"Resuming from page {start_page + 1}")
                    logger.info(f"Resuming processing from page {start_page + 1}")

        # Initialize system monitor
        system_monitor = None
        if self.enable_system_monitoring and output_path:
            system_monitor = SystemMonitor(output_path, interval=self.monitor_interval)
            system_monitor.start()

        # Extract hybrid data (text + images)
        pages_data = self.pdf_handler.extract_hybrid_data(
            pdf_path, max_pages, dpi
        )

        # Update monitor with total pages
        total_pages = len(pages_data)
        if system_monitor:
            system_monitor.update_progress(start_page, total_pages)

        results = []
        model = self.model_manager.get_current_model()

        if not model:
            raise RuntimeError("No model loaded in ModelManager")

        # Cache model name for incremental mode (since it gets unloaded between steps)
        model_name = self.model_manager.current_model_name

        # Wrap processing in try/finally to ensure cleanup
        try:
            for idx, (embedded_text, image, has_text) in enumerate(pages_data):
                page_num = idx + 1

                # Skip already processed pages if resuming
                if idx < start_page:
                    continue

                # Update monitor progress
                if system_monitor:
                    system_monitor.update_progress(idx, total_pages)

                if self.verbose:
                    progress_pct = ((idx + 1) / total_pages) * 100
                    print(f"Processing page {page_num}/{total_pages} ({progress_pct:.1f}%)...", end=" ", flush=True)

                # Use incremental mode if enabled
                if self.enable_incremental_mode and self.method != "extract":
                    result = self._process_incremental(
                        image, embedded_text, page_num,
                        model_name, has_text
                    )
                # Use OOM recovery wrapper if enabled
                elif self.enable_oom_recovery and self.method != "extract":
                    try:
                        # Try normal processing first
                        if self.force_ocr or self.method == "ocr":
                            result = self._process_ocr_only(image, page_num, model)
                        elif not has_text or len(embedded_text or "") < self.min_text_chars:
                            result = self._process_ocr_only(image, page_num, model)
                        else:  # auto or hybrid
                            result = self._process_hybrid(image, embedded_text or "", page_num, model)
                    except RuntimeError as e:
                        if "out of memory" in str(e).lower():
                            # OOM detected - use recovery mode
                            if self.verbose:
                                print("\n  OOM detected, attempting recovery...")
                            result = self._process_with_oom_recovery(
                                image, embedded_text, page_num, model, has_text
                            )
                        else:
                            raise
                # Normal processing (no special modes)
                else:
                    if self.force_ocr or self.method == "ocr":
                        result = self._process_ocr_only(image, page_num, model)
                    elif not has_text or len(embedded_text or "") < self.min_text_chars:
                        result = self._process_ocr_only(image, page_num, model)
                    elif self.method == "extract":
                        result = self._process_extract_only(embedded_text or "", page_num)
                    else:  # auto or hybrid
                        result = self._process_hybrid(image, embedded_text or "", page_num, model)
            
                results.append(result)

                if self.verbose:
                    print(f"{result.method.upper()} ({result.processing_time:.2f}s)", flush=True)

                # Write page result incrementally if output path provided
                if output_path and checkpoint_manager:
                    self._write_page_result(output_path, result, append=(idx > 0 or start_page > 0))

                    # Save checkpoint after each page
                    checkpoint_manager.save(idx, total_pages)

                # === NEW: Aggressive memory cleanup after each page ===
                if self.enable_memory_optimization:
                    # Force Python garbage collection
                    gc.collect()
                
                    # CUDA cleanup (if available)
                    if torch.cuda.is_available():
                        # Empty cache on all GPUs
                        torch.cuda.empty_cache()

                        # Synchronize all GPU operations
                        for device_id in range(torch.cuda.device_count()):
                            torch.cuda.synchronize(device_id)

                        # IPC memory cleanup (helps with shared memory)
                        try:
                            torch.cuda.ipc_collect()
                        except Exception:
                            pass  # Not available in all PyTorch versions

                        # Reset peak memory stats to clean slate
                        for device_id in range(torch.cuda.device_count()):
                            torch.cuda.reset_peak_memory_stats(device_id)

                        # Longer pause to let allocator fully settle
                        # This helps prevent fragmentation on next allocation
                        time.sleep(0.5)

                    # Clear all model caches
                    if self.gpu_strategy_manager:
                        for model_name, model_info in self.gpu_strategy_manager.loaded_models.items():
                            if hasattr(model_info, 'model_instance'):
                                model_instance = model_info.model_instance
                                if hasattr(model_instance, 'clear_cache'):
                                    model_instance.clear_cache()

                    # Every 10 pages, perform deep memory reset to combat fragmentation
                    if (idx + 1) % 10 == 0 and self.gpu_strategy_manager:
                        from ..models.loading_strategies import SingleGPUSequentialStrategy

                        # Only do deep reset for persistent strategies (not sequential)
                        if not isinstance(self.gpu_strategy_manager.current_strategy, SingleGPUSequentialStrategy):
                            if self.verbose:
                                print(f"\n  [Performing deep memory reset at page {idx + 1}]")

                            # Unload all models
                            for model_name in list(self.gpu_strategy_manager.loaded_models.keys()):
                                try:
                                    self.model_manager.unload_model(model_name)
                                except Exception as e:
                                    if self.verbose:
                                        print(f"    Warning: Failed to unload {model_name}: {e}")

                            # Force cleanup
                            gc.collect()
                            if torch.cuda.is_available():
                                torch.cuda.empty_cache()
                                torch.cuda.synchronize()

                            # Wait for allocator to settle
                            time.sleep(1.0)

                            # Reload models
                            try:
                                self.gpu_strategy_manager.initialize_for_hybrid_processing(
                                    ocr_model_name="deepseek-ocr",
                                    merge_model_name=self.merge_model_preference,
                                    dpi=dpi,
                                    enable_profiling=self.enable_memory_profiling,
                                    disable_crop_mode=self.disable_crop_mode,
                                    prefer_quality=self.prefer_quality
                                )
                                # Update model reference
                                model = self.model_manager.get_current_model()
                                if self.verbose:
                                    print(f"  [Deep memory reset completed]")
                            except Exception as e:
                                if self.verbose:
                                    print(f"    Warning: Failed to reload models: {e}")
                                raise

                    if self.verbose:
                        print(f"  [Memory cleanup completed]")

        finally:
            # Stop system monitor
            if system_monitor:
                system_monitor.stop()

            # Clear checkpoint on successful completion
            if checkpoint_manager and len(results) == total_pages:
                checkpoint_manager.clear()
                if self.verbose:
                    print("Processing completed successfully - checkpoint cleared")

        return results

    def _write_page_result(self, output_path: Path, result: PageResult, append: bool = False) -> None:
        """
        Write a single page result to output file.

        Args:
            output_path: Path to output file
            result: PageResult to write
            append: Whether to append (True) or overwrite (False)
        """
        mode = 'a' if append else 'w'

        # Build page metadata and text
        metadata = (
            f"<!-- Page {result.page_num} | "
            f"Method: {result.method.upper()} | "
            f"Time: {result.processing_time:.2f}s | "
            f"Chars: {len(result.text)} -->\n"
        )

        try:
            with open(output_path, mode, encoding='utf-8') as f:
                f.write(metadata)
                f.write(result.text)
                f.write("\n\n")
                f.flush()  # Force write to disk
        except IOError as e:
            logger.error(f"Failed to write page result to {output_path}: {e}")

    def _process_ocr_only(self, image, page_num, model) -> PageResult:
        """
        Process with OCR only.
        
        Args:
            image: PIL Image
            page_num: Page number
            model: VL model instance
            
        Returns:
            PageResult
        """
        start_time = time.time()
        
        # Get OCR model via strategy manager if available
        ocr_model = (self.gpu_strategy_manager.get_model_for_task("ocr")
                     if self.gpu_strategy_manager
                     else model)
        
        ocr_result = ocr_model.process_image(image, prompt_type="ocr")
        
        # Clear cache between inference passes
        if self.enable_memory_optimization:
            ocr_model.clear_cache()
        
        # Apply visual formatting if needed
        if self.output_format != "text":
            # Get format model via strategy manager if available
            format_model = (self.gpu_strategy_manager.get_model_for_task("format")
                           if self.gpu_strategy_manager
                           else model)
            
            format_result = format_model.format_with_visual(
                image=image,
                text=ocr_result.text,
                target_format=self.output_format,
                context=self.document_context
            )
            final_text = format_result.text
            format_time = format_result.processing_time
            
            # Clear cache after formatting
            if self.enable_memory_optimization:
                format_model.clear_cache()
        else:
            final_text = ocr_result.text
            format_time = 0
        
        processing_time = time.time() - start_time
        
        return PageResult(
            page_num=page_num,
            text=final_text,
            method="ocr",
            processing_time=processing_time,
            metadata={
                "ocr_time": ocr_result.processing_time,
                "format_time": format_time,
                "image_size": image.size,
                "memory_usage": ocr_result.metadata.get("memory_usage", {}),
            },
            output_format=self.output_format
        )
    
    def _process_extract_only(self, text, page_num) -> PageResult:
        """
        Process with text extraction only.
        
        Args:
            text: Embedded text
            page_num: Page number
            
        Returns:
            PageResult
        """
        start_time = time.time()
        
        # Just return the embedded text
        # Note: Extract-only mode doesn't apply visual formatting (no image available)
        processing_time = time.time() - start_time
        
        return PageResult(
            page_num=page_num,
            text=text,
            method="embedded",
            processing_time=processing_time,
            metadata={
                "text_length": len(text),
            },
            output_format=self.output_format
        )
    
    def _process_hybrid(
        self, 
        image, 
        embedded_text, 
        page_num, 
        model,
        structure: Optional[PageStructure] = None,
        few_shot_context: Optional[str] = None
    ) -> PageResult:
        """
        Hybrid processing: Extract + OCR + AI merge + Visual formatting.
        
        Args:
            image: PIL Image
            embedded_text: Embedded text from PDF
            page_num: Page number
            model: VL model instance
            structure: Optional PageStructure with spatial metadata
            few_shot_context: Optional few-shot examples from calibration
            
        Returns:
            PageResult
        """
        start_time = time.time()
        
        # === NEW: Start memory profiling if enabled ===
        start_mem = None
        device_id = 0
        
        if self.enable_memory_profiling and self.gpu_strategy_manager:
            profiler = self.gpu_strategy_manager.analyzer.profiler
            
            if profiler:
                # Determine which GPU the model is on
                if hasattr(model, 'model') and hasattr(model.model, 'device'):
                    device = model.model.device
                    if hasattr(device, 'index') and device.index is not None:
                        device_id = device.index
                
                # Start profiling
                start_mem = profiler.start_profiling(device_id)
        
        # Step 1: Get OCR text
        # Get OCR model via strategy manager if available
        ocr_model = (self.gpu_strategy_manager.get_model_for_task("ocr")
                     if self.gpu_strategy_manager
                     else model)
        
        ocr_result = ocr_model.process_image(image, prompt_type="ocr")
        ocr_text = ocr_result.text or ""

        # Log actual memory usage for validation
        if self.verbose and torch.cuda.is_available():
            try:
                device_id = 0
                if hasattr(ocr_model, 'model') and hasattr(ocr_model.model, 'device'):
                    device = ocr_model.model.device
                    if hasattr(device, 'index') and device.index is not None:
                        device_id = device.index
                actual_peak = torch.cuda.max_memory_allocated(device_id) / (1024**3)
                print(f"  [OCR VRAM peak]: {actual_peak:.2f}GB on GPU {device_id}")
                torch.cuda.reset_peak_memory_stats(device_id)
            except Exception:
                pass  # Silently fail if memory tracking unavailable

        # Clear cache between inference passes
        if self.enable_memory_optimization:
            ocr_model.clear_cache()
        
        # Prepare image for merge (annotated or original)
        merge_image = image
        annotation_desc = ""
        
        if self.enable_bbox_annotations and structure and self.image_annotator:
            merge_image, annotation_desc = self.image_annotator.annotate_image(
                image, structure
            )
        
        # Step 2: Use model to merge both texts with optional spatial enhancement
        # Get merge model via strategy manager if available
        merge_model = (self.gpu_strategy_manager.get_model_for_task("merge")
                       if self.gpu_strategy_manager
                       else model)
        
        # Note: spatial_hints requires structured extraction which is not yet implemented in process_pdf
        # For now, fall back to regular merge
        if False and self.enable_spatial_hints and structure and self.spatial_prompt_builder:
            # Get base prompt from model
            base_prompt = getattr(merge_model, 'prompts', {}).get("merge", "")
            
            # Build enhanced prompt
            if annotation_desc:
                enhanced_prompt = self.spatial_prompt_builder.enhance_merge_prompt_with_annotations(
                    base_prompt, structure, annotation_desc, embedded_text, ocr_text
                )
            else:
                enhanced_prompt = self.spatial_prompt_builder.enhance_merge_prompt(
                    base_prompt, structure, embedded_text, ocr_text
                )
            
            # Add few-shot examples if provided
            if few_shot_context:
                enhanced_prompt = f"""{enhanced_prompt}

REFERENCE EXAMPLES FROM PREVIOUS PAGES:
{few_shot_context}

Match this formatting style and structure."""
            
            # Use custom prompt method
            merge_result = merge_model.merge_texts_with_prompt(
                merge_image, enhanced_prompt
            )
        else:
            # Original merge without spatial hints
            merge_result = merge_model.merge_texts(
                merge_image,
                embedded_text=embedded_text,
                ocr_text=ocr_text
            )
        
        # Clear cache after merge
        if self.enable_memory_optimization:
            merge_model.clear_cache()
        
        # Log actual memory usage for validation
        if self.verbose and torch.cuda.is_available():
            try:
                device_id = 0
                if hasattr(merge_model, 'model') and hasattr(merge_model.model, 'device'):
                    device = merge_model.model.device
                    if hasattr(device, 'index') and device.index is not None:
                        device_id = device.index
                actual_peak = torch.cuda.max_memory_allocated(device_id) / (1024**3)
                print(f"  [Merge VRAM peak]: {actual_peak:.2f}GB on GPU {device_id}")
                torch.cuda.reset_peak_memory_stats(device_id)
            except Exception:
                pass  # Silently fail if memory tracking unavailable

        # Debug: Check merge_result
        if self.verbose:
            print(f"[DEBUG] Merge result text length: {len(merge_result.text) if merge_result.text else 0}")
        
        # Step 3: Apply visual formatting if needed
        if self.output_format != "text":
            # Get format model via strategy manager if available
            format_model = (self.gpu_strategy_manager.get_model_for_task("format")
                           if self.gpu_strategy_manager
                           else model)
            
            format_result = format_model.format_with_visual(
                image=image,
                text=merge_result.text,
                target_format=self.output_format,
                context=self.document_context
            )
            final_text = format_result.text
            format_time = format_result.processing_time
            
            # Clear cache after formatting
            if self.enable_memory_optimization:
                format_model.clear_cache()
        else:
            final_text = merge_result.text
            format_time = 0

        # Step 4: Validation (if enabled)
        validation_time = 0
        refinement_time = 0
        is_valid = None
        combined_issues = None

        if self.enable_validation:
            validation_start = time.time()

            # Determine which models are available for validation
            available_models = self._get_available_models_for_validation()

            if len(available_models) >= 2:
                # Dual validation - cross-check with both models
                if self.verbose:
                    print(f"[VALIDATION] Using dual-validation with {len(available_models)} models")

                is_valid, combined_issues = self._dual_validate(
                    image, final_text, available_models
                )
            else:
                # Single validation with format_model (already loaded)
                if self.verbose:
                    print(f"[VALIDATION] Using single-model validation")

                format_model = (self.gpu_strategy_manager.get_model_for_task("format")
                               if self.gpu_strategy_manager
                               else model)

                # Safety check: ensure model exists and has validation capability
                if format_model and hasattr(format_model, 'validate_extraction'):
                    is_valid, issues = format_model.validate_extraction(
                        image=image,
                        extracted_text=final_text
                    )
                    combined_issues = issues
                else:
                    # Skip validation if model not available
                    if self.verbose:
                        print(f"[VALIDATION] Warning: No model with validation capability available, skipping validation")
                    is_valid = True  # Assume valid if can't validate
                    combined_issues = ""

            validation_time = time.time() - validation_start

            if self.enable_memory_optimization:
                if self.gpu_strategy_manager:
                    format_model = self.gpu_strategy_manager.get_model_for_task("format")
                    if format_model:
                        format_model.clear_cache()
                else:
                    model.clear_cache()

            # Step 5: Refinement (if validation failed)
            if not is_valid:
                refinement_start = time.time()

                if self.verbose:
                    print(f"[VALIDATION] Issues detected: {combined_issues}")
                    print(f"[REFINEMENT] Starting refinement pass...")

                # Get DeepSeek-OCR for refinement (will be loaded for next page anyway)
                refinement_model = (self.gpu_strategy_manager.get_model_for_task("ocr")
                                   if self.gpu_strategy_manager
                                   else model)

                # Safety check: ensure model exists and has refinement capability
                if refinement_model and hasattr(refinement_model, 'refine_extraction'):
                    refinement_result = refinement_model.refine_extraction(
                        image=image,
                        initial_text=final_text,
                        issues=combined_issues,
                        context=self.document_context
                    )

                    final_text = refinement_result.text
                    refinement_time = time.time() - refinement_start

                    if self.enable_memory_optimization:
                        refinement_model.clear_cache()

                    if self.verbose:
                        print(f"[REFINEMENT] Completed in {refinement_time:.2f}s")
                else:
                    # Can't refine without proper model
                    if self.verbose:
                        print(f"[REFINEMENT] Warning: No model with refinement capability, keeping original text")
                    refinement_time = 0.0
            else:
                if self.verbose:
                    print(f"[VALIDATION] Extraction validated successfully")

        if self.verbose:
            print(f"[DEBUG] Final text length: {len(final_text) if final_text else 0}")

        processing_time = time.time() - start_time
        
        # === NEW: End memory profiling and record ===
        if self.enable_memory_profiling and self.gpu_strategy_manager:
            profiler = self.gpu_strategy_manager.analyzer.profiler
            
            if profiler and start_mem is not None:
                # Get peak memory used
                peak_mem_gb = profiler.end_profiling(device_id, start_mem)
                
                # Record profile
                profiler.add_profile(
                    dpi=300,  # Use actual DPI from pdf_handler if available
                    page_size="legal",  # Could make this dynamic
                    peak_memory_gb=peak_mem_gb,
                    model_name=self.model_manager.current_model_name or "unknown",
                    crop_mode=not self.disable_crop_mode
                )
                
                if self.verbose:
                    print(f"  [Memory Profile] Peak: {peak_mem_gb:.2f}GB")
        
        return PageResult(
            page_num=page_num,
            text=final_text or "",
            method="hybrid",
            processing_time=processing_time,
            metadata={
                "embedded_text_length": len(embedded_text or ""),
                "ocr_text_length": len(ocr_text or ""),
                "ocr_time": ocr_result.processing_time,
                "merge_time": merge_result.processing_time,
                "format_time": format_time,
                "validation_enabled": self.enable_validation,
                "validation_passed": is_valid if self.enable_validation else None,
                "validation_time": validation_time,
                "refinement_time": refinement_time,
                "issues_detected": combined_issues if self.enable_validation and not is_valid else None,
                "total_time": processing_time,
                "image_size": image.size,
                "memory_usage": merge_result.metadata.get("memory_usage", {}),
            },
            output_format=self.output_format
        )
    
    def _process_with_oom_recovery(
        self,
        image,
        embedded_text: str,
        page_num: int,
        model,
        has_text: bool
    ) -> PageResult:
        """
        Process page with automatic OOM recovery via image resizing.
        
        Attempts processing with progressively smaller image sizes if OOM occurs.
        
        Args:
            image: PIL Image
            embedded_text: Embedded text from PDF
            page_num: Page number
            model: VL model instance
            has_text: Whether page has embedded text
            
        Returns:
            PageResult
        """
        import torch
        import gc
        
        scale_factors = [1.0, 0.75, 0.5, 0.35, 0.25]
        last_error = None
        
        for scale in scale_factors:
            try:
                # Resize image if needed
                if scale < 1.0:
                    resized_image = self.pdf_handler.resize_image_by_factor(image, scale)
                    if self.verbose:
                        print(f"  Retrying with {int(scale*100)}% image size...")
                else:
                    resized_image = image
                
                # Clear cache before attempt
                if self.enable_memory_optimization:
                    torch.cuda.empty_cache()
                    gc.collect()
                
                # Choose processing method
                if self.force_ocr or not has_text or len(embedded_text) < self.min_text_chars:
                    return self._process_ocr_only(resized_image, page_num, model)
                elif self.method == "extract":
                    return self._process_extract_only(embedded_text, page_num)
                else:
                    return self._process_hybrid(resized_image, embedded_text, page_num, model)
                    
            except RuntimeError as e:
                error_msg = str(e).lower()
                if "out of memory" in error_msg or "cuda" in error_msg:
                    last_error = e
                    if scale == scale_factors[-1]:
                        # Last attempt failed
                        break
                    # Try next scale factor
                    continue
                else:
                    # Not an OOM error, re-raise
                    raise
        
        # If all attempts failed, raise the last error
        raise RuntimeError(
            f"OOM error persisted after all resize attempts (tried scales: {scale_factors}). "
            f"Last error: {last_error}"
        )
    
    def _process_incremental(
        self,
        image,
        embedded_text: str,
        page_num: int,
        model_name: str,
        has_text: bool
    ) -> PageResult:
        """
        Process with incremental mode - unload/reload model between steps.
        
        Most memory-efficient but slowest method. Unloads the model between
        each inference pass to minimize peak memory usage.
        
        Args:
            image: PIL Image
            embedded_text: Embedded text from PDF
            page_num: Page number
            model_name: Name of model to use
            has_text: Whether page has embedded text
            
        Returns:
            PageResult
        """
        import time
        
        start_time = time.time()
        
        # Decide if we need OCR
        need_ocr = self.force_ocr or not has_text or len(embedded_text) < self.min_text_chars
        
        if self.method == "extract" and not need_ocr:
            # Pure extraction mode - no model needed
            return self._process_extract_only(embedded_text, page_num)
        
        # Step 1: OCR
        self.model_manager.load_model(model_name)
        model = self.model_manager.get_current_model()
        ocr_result = model.process_image(image, prompt_type="ocr")
        ocr_text = ocr_result.text
        ocr_time = ocr_result.processing_time
        self.model_manager.unload_model(model_name)
        
        if not has_text or len(embedded_text) < self.min_text_chars:
            # OCR-only path with formatting
            if self.output_format != "text":
                # Step 2: Format
                self.model_manager.load_model(model_name)
                model = self.model_manager.get_current_model()
                format_result = model.format_with_visual(
                    image=image,
                    text=ocr_text,
                    target_format=self.output_format,
                    context=self.document_context
                )
                final_text = format_result.text
                format_time = format_result.processing_time
                self.model_manager.unload_model(model_name)
            else:
                final_text = ocr_text
                format_time = 0
            
            processing_time = time.time() - start_time
            
            return PageResult(
                page_num=page_num,
                text=final_text,
                method="ocr",
                processing_time=processing_time,
                metadata={
                    "ocr_time": ocr_time,
                    "format_time": format_time,
                    "image_size": image.size,
                    "incremental_mode": True,
                },
                output_format=self.output_format
            )
        
        # Hybrid path: Step 2: Merge
        self.model_manager.load_model(model_name)
        model = self.model_manager.get_current_model()
        merge_result = model.merge_texts(
            image=image,
            embedded_text=embedded_text,
            ocr_text=ocr_text
        )
        merged_text = merge_result.text
        merge_time = merge_result.processing_time
        self.model_manager.unload_model(model_name)
        
        # Step 3: Format (if needed)
        if self.output_format != "text":
            self.model_manager.load_model(model_name)
            model = self.model_manager.get_current_model()
            format_result = model.format_with_visual(
                image=image,
                text=merged_text,
                target_format=self.output_format,
                context=self.document_context
            )
            final_text = format_result.text
            format_time = format_result.processing_time
            self.model_manager.unload_model(model_name)
        else:
            final_text = merged_text
            format_time = 0
        
        processing_time = time.time() - start_time
        
        return PageResult(
            page_num=page_num,
            text=final_text,
            method="hybrid",
            processing_time=processing_time,
            metadata={
                "embedded_text_length": len(embedded_text),
                "ocr_text_length": len(ocr_text),
                "ocr_time": ocr_time,
                "merge_time": merge_time,
                "format_time": format_time,
                "total_time": processing_time,
                "image_size": image.size,
                "incremental_mode": True,
            },
            output_format=self.output_format
        )
    
    def _process_page_with_structure(
        self,
        structure: PageStructure,
        model,
        few_shot_context: Optional[str] = None
    ) -> PageResult:
        """
        Process a single page using its structure.
        
        Args:
            structure: PageStructure with spatial metadata
            model: VL model instance
            few_shot_context: Optional few-shot examples from calibration
            
        Returns:
            PageResult for the processed page
        """
        # Determine processing method based on structure
        has_digital_text = len(structure.raw_digital_text.strip()) >= self.min_text_chars
        
        if not has_digital_text or self.force_ocr or self.method == "ocr":
            return self._process_ocr_only(structure.image, structure.page_num, model)
        elif self.method == "extract":
            return self._process_extract_only(structure.raw_digital_text, structure.page_num)
        else:
            # Hybrid path with structure and optional few-shot context
            return self._process_hybrid(
                structure.image,
                structure.raw_digital_text,
                structure.page_num,
                model,
                structure=structure,
                few_shot_context=few_shot_context
            )
    
    def process_pdf_with_calibration(
        self,
        pdf_path: Path,
        calibration_config,
        approval_callback: Optional[Callable] = None,
        max_pages: Optional[int] = None,
        dpi: int = 300
    ) -> List[PageResult]:
        """
        Process PDF with calibration phase.
        
        Args:
            pdf_path: Path to PDF file
            calibration_config: CalibrationConfig object
            approval_callback: Function to handle approval (for UI integration)
            max_pages: Max pages to process total
            dpi: DPI for rendering
        
        Returns:
            List of PageResult for all pages
        """
        from ..api.calibration_service import CalibrationService
        
        calibration_service = CalibrationService()
        
        # Phase 1: Process calibration pages
        if self.verbose:
            print(f"\nCalibrating with first {calibration_config.num_calibration_pages} pages...")
        
        calibration = calibration_service.process_calibration_pages(
            pdf_path, calibration_config, self, self.model_manager
        )
        
        # Phase 2: Get approval (via callback or default to approved)
        if approval_callback and calibration_config.require_approval:
            approved, feedback = approval_callback(calibration)
            calibration.approved = approved
            calibration.user_feedback = feedback
            
            if not approved:
                raise ValueError(f"Calibration not approved. Feedback: {feedback}")
        else:
            calibration.approved = True
        
        # Phase 3: Build few-shot examples
        few_shot_examples = calibration_service.build_few_shot_examples(calibration)
        
        if self.verbose:
            print(f"Processing remaining pages with calibrated format...")
        
        # Phase 4: Process remaining pages with examples
        all_structures = self.pdf_handler.extract_hybrid_data_structured(
            pdf_path, max_pages, dpi
        )
        
        results = list(calibration.pages)  # Start with calibration results
        
        # Process remaining pages with few-shot context
        model = self.model_manager.get_current_model()
        for structure in all_structures[calibration_config.num_calibration_pages:]:
            if self.verbose:
                print(f"Processing page {structure.page_num}...", end=" ")
            
            result = self._process_page_with_structure(
                structure, model, few_shot_context=few_shot_examples
            )
            results.append(result)
            
            if self.verbose:
                print(f"{result.method.upper()} ({result.processing_time:.2f}s)")

        return results

    def _get_available_models_for_validation(self):
        """
        Get list of currently loaded models available for validation.

        Checks which models are loaded in memory and have the validate_extraction
        method available.

        Returns:
            List of model instances that can perform validation
        """
        available = []

        if self.gpu_strategy_manager:
            loaded = self.gpu_strategy_manager.loaded_models

            for model_info in loaded.values():
                model_instance = model_info.model_instance

                # Check if model has validation capability
                if hasattr(model_instance, 'validate_extraction'):
                    available.append(model_instance)

        return available

    def _dual_validate(
        self,
        image,
        text: str,
        models
    ) -> Tuple[bool, str]:
        """
        Run validation with multiple models and combine results using ensemble logic.

        Validation Logic:
        - Both VALID → return (True, "") - High confidence
        - One INVALID → return (False, invalid_issues) - One model caught issues
        - Both INVALID → return (False, merged_issues) - Multiple issues detected

        Args:
            image: Page image
            text: Extracted text to validate
            models: List of model instances to use for validation (max 2)

        Returns:
            Tuple of (is_valid, combined_issues)
        """
        # Run validation on up to 2 models
        results = []
        for model in models[:2]:
            is_valid, issues = model.validate_extraction(image, text)
            results.append((is_valid, issues, model.model_id))

            if self.verbose:
                status = "✓ VALID" if is_valid else f"✗ INVALID: {issues}"
                print(f"  [{model.model_id}] {status}")

        # Count valid results
        valid_count = sum(1 for v, _, _ in results if v)

        if valid_count == len(results):
            # All models agree it's valid
            if self.verbose:
                print(f"  [ENSEMBLE] All {len(results)} models agree: VALID")
            return True, ""

        elif valid_count == 0:
            # All models found issues - merge descriptions
            all_issues = [issues for _, issues, _ in results if issues]
            combined = " | ".join(all_issues)

            if self.verbose:
                print(f"  [ENSEMBLE] All {len(results)} models found issues")

            return False, combined

        else:
            # Disagreement - use the invalid one's issues (err on side of caution)
            invalid_issue = next(issues for v, issues, _ in results if not v)
            invalid_model = next(mid for v, _, mid in results if not v)

            if self.verbose:
                print(f"  [ENSEMBLE] Disagreement - using issues from {invalid_model}")

            return False, invalid_issue

