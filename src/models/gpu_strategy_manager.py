"""GPU strategy manager for adaptive model loading."""
from dataclasses import dataclass
from typing import List, Optional, Dict, Literal, Any, Tuple
import psutil  # For RAM detection in strategy selection
from .gpu_memory_analyzer import (
    GPUMemoryAnalyzer,
    ModelMemoryRequirement,
    DEEPSEEK_RESOLUTION_CONFIGS,
    calculate_deepseek_overhead
)
from .loading_strategies import (
    ModelLoadingStrategy,
    SingleGPUPersistentStrategy,
    DualGPUPersistentStrategy,
    SingleGPUSequentialStrategy,
    QuantizedFallbackStrategy
)


StrategyType = Literal["auto", "dual", "sequential", "sharded"]


@dataclass
class ConfigurationCandidate:
    """
    Represents a potential GPU configuration to try during quality-first validation.

    This class encapsulates all parameters needed to test a specific configuration:
    - Model choices (merge model and OCR resolution mode)
    - GPU strategy (single/dual/sequential)
    - Quality and speed metrics for prioritization
    - Memory estimates for preflight checks
    """
    merge_model: Optional[str]  # "qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b", or None (for OCR-only stages)
    ocr_model: Optional[str]  # "deepseek-ocr" or None (for merge-only stages)
    deepseek_resolution_mode: str  # "gundam", "large", "base", "small", "tiny"
    crop_mode_enabled: bool  # Affects memory significantly (7.5GB vs 3.5GB base)
    strategy_type: str  # "single_gpu_persistent", "dual_gpu_persistent", "sequential"
    quality_score: float  # Higher is better quality (0-100 scale)
    speed_score: float  # Higher is faster (0-100 scale)
    estimated_memory_gb: float  # Estimated peak memory (for preflight checks)
    vision_tokens: int  # Number of vision tokens (for reference)
    device_ids: List[int]  # Which GPUs to use
    stage: Optional[str] = None  # "ocr", "merge", or None (both models - hybrid mode)

# GPU Memory Safety Buffers (fixed GB, not percentage-based)
# These account for: PyTorch allocator overhead (~1GB), dynamic inference spikes (~1.5GB),
# measurement uncertainty (~0.5-1GB), and system reserves (~0.5GB)
SINGLE_GPU_BUFFER_GB = 4.0  # Conservative: both models loaded, highest memory pressure
DUAL_GPU_BUFFER_GB = 3.0    # Moderate: one model per GPU, shared load
SEQUENTIAL_BUFFER_GB = 2.5  # Permissive: one model at a time, unload/reload overhead

# CPU Offloading Strategy:
# - Reserve CPU_OFFLOAD_BUFFER_GB for system (fixed buffer, not percentage)
# - Only enable if available RAM >= CPU_OFFLOAD_MIN_AVAILABLE_GB
# - On WSL, apply WSL_RAM_REDUCTION_FACTOR due to limited RAM access
CPU_OFFLOAD_BUFFER_GB = 20.0        # Reserve for OS/system processes
CPU_OFFLOAD_MIN_AVAILABLE_GB = 30.0  # Minimum RAM to enable CPU offloading
WSL_RAM_REDUCTION_FACTOR = 0.85      # WSL may not have access to full RAM


class GPUStrategyManager:
    """Manage adaptive GPU loading strategy based on hardware analysis."""
    
    def __init__(
        self,
        model_manager,
        strategy_preference: StrategyType = "auto",
        verbose: bool = False,
        enable_inference_profiling: bool = True
    ):
        """
        Initialize GPU strategy manager.

        Args:
            model_manager: ModelManager instance
            strategy_preference: User's strategy preference
            verbose: Print strategy decisions
            enable_inference_profiling: Enable runtime memory profiling
        """
        self.model_manager = model_manager
        self.strategy_preference = strategy_preference
        self.verbose = verbose
        self.analyzer = GPUMemoryAnalyzer()

        self.current_strategy: Optional[ModelLoadingStrategy] = None
        self.loaded_models: Dict[str, Any] = {}
        self.disable_crop_mode: bool = False  # Store for model loading

        # Profiling integration
        self.enable_inference_profiling = enable_inference_profiling
        self.inference_profiler = None
        if enable_inference_profiling:
            from ..utils.memory_profiler import InferenceProfiler
            self.inference_profiler = InferenceProfiler()
    
    def initialize_for_hybrid_processing(
        self,
        ocr_model_name: str = "deepseek-ocr",
        merge_model_name: Optional[str] = None,
        dpi: int = 300,
        enable_profiling: bool = False,
        disable_crop_mode: bool = False,
        prefer_quality: bool = True,
        use_validation_based_selection: bool = True
    ):
        """
        Initialize models for hybrid PDF processing.

        Analyzes hardware and selects optimal strategy for loading
        OCR and merge models.

        Args:
            ocr_model_name: Name of model to use for OCR
            merge_model_name: Name of model to use for merge/format (None = auto-select)
            dpi: DPI setting for page rendering (affects memory)
            enable_profiling: Enable dynamic memory profiling
            disable_crop_mode: Disable crop mode in DeepSeek (ignored if use_validation_based_selection=True)
            prefer_quality: Prefer higher quality models when auto-selecting
            use_validation_based_selection: Use new quality-first validation approach (recommended)
        """
        # Store crop mode setting for model loading
        self.disable_crop_mode = disable_crop_mode

        # Update analyzer with DPI and profiling settings
        self.analyzer = GPUMemoryAnalyzer(dpi=dpi, enable_profiling=enable_profiling)

        # === NEW QUALITY-FIRST VALIDATION-BASED SELECTION ===
        if use_validation_based_selection and merge_model_name is None and prefer_quality:
            if self.verbose:
                print(f"\n[Model Selection] Using quality-first validation-based selection")
                print(f"  DPI: {dpi}")
                print(f"  Will test all configurations from highest quality to lowest")

            # Calculate worst-case page dimensions (Legal size at specified DPI)
            worst_case_dims = (int(14.0 * dpi), int(8.5 * dpi))  # height, width

            # Run validation-based selection
            config = self._select_configuration_with_validation(
                dpi=dpi,
                worst_case_dimensions=worst_case_dims
            )

            if config is None:
                raise RuntimeError(
                    "No suitable GPU configuration found after testing all candidates. "
                    "This may indicate insufficient VRAM or incorrect memory calculations."
                )

            # Unpack validated configuration
            merge_model_name = config['merge_model']
            deepseek_resolution_mode = config['deepseek_resolution_mode']
            crop_mode_enabled = config['crop_mode_enabled']
            strategy_type = config['strategy_type']
            device_ids = config['device_ids']

            if self.verbose:
                print(f"\n[Validated Configuration]")
                print(f"  Merge Model: {merge_model_name}")
                print(f"  DeepSeek Resolution: {deepseek_resolution_mode}")
                print(f"  Crop Mode: {'enabled' if crop_mode_enabled else 'disabled'}")
                print(f"  Strategy: {strategy_type}")
                print(f"  Quality Score: {config['quality_score']:.1f}")
                print(f"  Actual Peak Memory: {config['actual_peak_gb']:.2f}GB")

            # Store validated settings
            self.selected_merge_model = merge_model_name
            self.selected_deepseek_resolution = deepseek_resolution_mode
            self.disable_crop_mode = not crop_mode_enabled

            # Build task mapping
            task_mapping = {
                "ocr": ocr_model_name,
                "merge": merge_model_name,
                "format": merge_model_name
            }

            # Create appropriate strategy based on validated configuration
            if strategy_type == "single_gpu_persistent":
                strategy = SingleGPUPersistentStrategy(device_ids[0], task_mapping)
            elif strategy_type == "dual_gpu_persistent":
                # Create assignment for dual GPU
                assignment = {
                    merge_model_name: device_ids[0],
                    ocr_model_name: device_ids[1] if len(device_ids) > 1 else device_ids[0]
                }
                strategy = DualGPUPersistentStrategy(assignment, task_mapping)
            else:  # sequential
                strategy = SingleGPUSequentialStrategy(device_ids[0], task_mapping)

            self.current_strategy = strategy

            # Load models with validated configuration
            model_names = [ocr_model_name, merge_model_name]

            # Pass resolution mode and crop mode to model loading
            # TODO: Update loading strategies to accept deepseek_resolution_mode parameter
            # For now, load without resolution mode parameter (will use default)
            self.loaded_models = strategy.load_models(
                self.model_manager,
                model_names,
                self.model_manager.model_configs,
                force_disable_crop=self.disable_crop_mode
                # deepseek_resolution_mode=deepseek_resolution_mode  # TODO: Add support
            )

            if self.verbose:
                print(f"\n[Models Loaded Successfully]")
                for name, info in self.loaded_models.items():
                    print(f"  {name}: GPU {info.device_ids}, {info.vram_used_gb:.1f}GB")

            return  # Exit early - validation-based path complete

        # === LEGACY PATH (when not using validation-based selection) ===
        # Smart model selection if not specified
        if merge_model_name is None:
            if prefer_quality:
                # Try 7B first, fall back to 2B
                merge_model_name = self._select_optimal_merge_model(
                    ocr_model_name, dpi, disable_crop_mode
                )
            else:
                # User prioritizes speed - use 2B
                merge_model_name = "qwen3-vl-2b"
                if self.verbose:
                    print(f"[Model Selection] Speed priority: using qwen3-vl-2b")
        else:
            if self.verbose:
                print(f"[Model Selection] User-specified: {merge_model_name}")

        # Store selected model for strategies to use
        self.selected_merge_model = merge_model_name

        runtime_overhead = self.analyzer.runtime_overhead_gb

        # Adjust runtime overhead if crop mode disabled
        if disable_crop_mode and ocr_model_name == "deepseek-ocr":
            # Without crop mode: ~2x less memory
            runtime_overhead = runtime_overhead * 0.47  # 3.5GB / 7.5GB ≈ 0.47
            if self.verbose:
                print(f"[GPU Strategy] Crop mode disabled, adjusted overhead: {runtime_overhead:.2f}GB")

        model_names = [ocr_model_name, merge_model_name]

        # Build model requirements
        requirements = []
        for name in model_names:
            config = self.model_manager.model_configs[name]
            vram_str = config.get("vram_requirement", "6GB")
            vram_gb = float(vram_str.replace("GB", "").split("-")[0])

            # Add runtime overhead to OCR model (it processes images)
            # Merge model also processes images with crops (not just text), so needs 75% overhead
            overhead = runtime_overhead if name == ocr_model_name else runtime_overhead * 0.75

            requirements.append(
                ModelMemoryRequirement(name, vram_gb, runtime_overhead_gb=overhead)
            )

        # PREFLIGHT VALIDATION: Check requirements against historical profiles
        # This ensures learned data influences strategy selection conservatively
        requirements = self._validate_requirements_with_profiles(
            requirements, dpi, disable_crop_mode
        )

        # Build dynamic task mapping based on selected models
        task_mapping = {
            "ocr": ocr_model_name,
            "merge": merge_model_name,
            "format": merge_model_name
        }

        # Determine strategy
        if self.strategy_preference == "dual":
            strategy = self._force_dual_gpu_strategy(requirements, task_mapping)
        elif self.strategy_preference == "sequential":
            strategy = self._force_sequential_strategy(task_mapping)
        elif self.strategy_preference == "sharded":
            # Sharded strategy has been removed - fall back to auto detection
            if self.verbose:
                print("  ⚠️ Sharded strategy is no longer supported, using auto-detection instead")
            strategy = self._auto_detect_strategy(requirements, task_mapping)
        else:  # auto
            strategy = self._auto_detect_strategy(requirements, task_mapping)
        
        if self.verbose:
            print(f"\n[Memory Analysis]")
            print(f"  Model weights: {sum(r.base_vram_gb for r in requirements):.2f}GB")
            print(f"  Max runtime overhead: {max(r.runtime_overhead_gb for r in requirements):.2f}GB")
            print(f"  Peak single-GPU: {sum(r.base_vram_gb for r in requirements) + max(r.runtime_overhead_gb for r in requirements):.2f}GB")
            print(f"\nGPU Strategy: {strategy.name()}")
            print(f"GPUs detected: {len(self.analyzer.gpus)}")
            for gpu in self.analyzer.gpus:
                print(f"  GPU {gpu.device_id}: {gpu.name} - "
                      f"{gpu.free_memory_gb:.1f}GB free")
        
        self.current_strategy = strategy

        # Load models with fallback chain for OOM resilience
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                if self.verbose and attempt > 0:
                    print(f"\n[Attempt {attempt + 1}/{max_attempts}] Loading models with {strategy.name()}...")

                self.loaded_models = strategy.load_models(
                    self.model_manager,
                    model_names,
                    self.model_manager.model_configs,
                    force_disable_crop=self.disable_crop_mode
                )

                # Success!
                if self.verbose:
                    if attempt > 0:
                        print(f"✓ Successfully loaded models after {attempt + 1} attempts")
                    for name, info in self.loaded_models.items():
                        print(f"  {name}: GPU {info.device_ids}, "
                              f"{info.vram_used_gb:.1f}GB, "
                              f"quant={info.quantization}")
                break

            except RuntimeError as e:
                # Check if it's a CUDA OOM error
                if "out of memory" in str(e).lower() or "oom" in str(e).lower():
                    last_error = e

                    if attempt < max_attempts - 1:
                        if self.verbose:
                            print(f"\n⚠️ CUDA Out of Memory during model loading")
                            print(f"   Error: {str(e)[:100]}...")

                        # Try fallback to safer strategy
                        fallback_strategy = self._fallback_to_safer_strategy(
                            strategy, requirements, task_mapping
                        )

                        if fallback_strategy:
                            strategy = fallback_strategy
                            self.current_strategy = strategy
                            if self.verbose:
                                print(f"   Retrying with {strategy.name()}")
                        else:
                            # No fallback available
                            if self.verbose:
                                print(f"   ✗ No fallback strategy available")
                            raise
                    else:
                        # Out of attempts
                        if self.verbose:
                            print(f"\n✗ Failed to load models after {max_attempts} attempts")
                        raise
                else:
                    # Not OOM, some other error - don't retry
                    raise
    
    def initialize_for_stage_processing(
        self,
        stage_name: str,
        model_name: str,
        dpi: int,
        enable_profiling: bool = False,
        deepseek_resolution_mode: Optional[str] = None,
        disable_crop_mode: bool = False,
        prefer_quality: bool = True,
        use_validation_based_selection: bool = True
    ) -> Dict[str, Any]:
        """
        Initialize GPU strategy for a single pipeline stage.

        This method is called ONCE per stage with the validated configuration.
        Unlike initialize_for_hybrid_processing(), it only loads one model.

        Args:
            stage_name: "ocr" or "merge"
            model_name: Model to use ("deepseek-ocr", "qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b")
            dpi: DPI setting
            enable_profiling: Enable memory profiling
            deepseek_resolution_mode: Resolution mode for DeepSeek (if applicable)
            disable_crop_mode: Disable crop mode for DeepSeek (if applicable)
            prefer_quality: Prefer quality over speed
            use_validation_based_selection: Use quality-first validation

        Returns:
            Dict with selected configuration metadata:
            {
                'model_name': str,
                'strategy_type': str,
                'device_ids': List[int],
                'actual_peak_gb': float,
                'deepseek_resolution_mode': str (if applicable),
                'crop_mode_enabled': bool (if applicable)
            }
        """
        # Store crop mode setting
        self.disable_crop_mode = disable_crop_mode

        # Update analyzer with DPI
        self.analyzer = GPUMemoryAnalyzer(dpi=dpi, enable_profiling=enable_profiling)

        if self.verbose:
            print(f"\n[Stage Initialization] Stage: {stage_name}, Model: {model_name}")
            print(f"  DPI: {dpi}")
            if stage_name == "ocr":
                print(f"  Resolution mode: {deepseek_resolution_mode}")
                print(f"  Crop mode: {'disabled' if disable_crop_mode else 'enabled'}")

        # If validation-based selection is enabled, run preflight for this stage
        if use_validation_based_selection:
            if self.verbose:
                print(f"\n[Stage Initialization] Running validation-based selection for {stage_name} stage")

            # Build candidates for this stage
            candidates = self._build_configuration_candidates(
                dpi=dpi,
                stage=stage_name,
                ocr_model=model_name if stage_name == "ocr" else "deepseek-ocr",
                merge_model_options=[model_name] if stage_name == "merge" else None
            )

            # Select best configuration
            config = self._select_stage_configuration_with_validation(
                stage_name=stage_name,
                candidates=candidates,
                dpi=dpi
            )

            if config is None:
                raise RuntimeError(
                    f"No suitable GPU configuration found for {stage_name} stage after testing all candidates."
                )

            # Unpack configuration
            strategy_type = config['strategy_type']
            device_ids = config['device_ids']

            if stage_name == "ocr":
                deepseek_resolution_mode = config['resolution_mode']
                crop_mode_enabled = config['crop_mode']
                self.disable_crop_mode = not crop_mode_enabled

            if self.verbose:
                print(f"\n[Stage Initialization] Selected configuration:")
                print(f"  Strategy: {strategy_type}")
                print(f"  Device IDs: {device_ids}")
                print(f"  Quality Score: {config['quality_score']:.1f}")
                print(f"  Actual Peak: {config['actual_peak_gb']:.2f}GB")

        else:
            # Legacy path: auto-detect strategy without validation
            if self.verbose:
                print(f"\n[Stage Initialization] Auto-detecting strategy (legacy mode)")

            # Build requirement for single model
            config_dict = self.model_manager.model_configs[model_name]
            vram_str = config_dict.get("vram_requirement", "6GB")
            vram_gb = float(vram_str.replace("GB", "").split("-")[0])

            runtime_overhead = self.analyzer.runtime_overhead_gb
            if disable_crop_mode and model_name == "deepseek-ocr":
                runtime_overhead *= 0.47

            requirement = ModelMemoryRequirement(
                model_name=model_name,
                base_vram_gb=vram_gb,
                runtime_overhead_gb=runtime_overhead
            )

            # Auto-detect strategy
            task_mapping = {
                "ocr": model_name if stage_name == "ocr" else None,
                "merge": model_name if stage_name == "merge" else None,
                "format": model_name if stage_name == "merge" else None
            }

            strategy = self._auto_detect_strategy([requirement], task_mapping)
            strategy_type = strategy.name()

            # Extract device_ids from auto-detected strategy
            if hasattr(strategy, 'gpu_id'):
                # Single/Sequential strategies have gpu_id
                device_ids = [strategy.gpu_id]
            elif hasattr(strategy, 'gpu_assignment'):
                # Dual GPU strategy has gpu_assignment
                device_ids = list(set(strategy.gpu_assignment.values()))
            else:
                # Fallback to GPU 0
                device_ids = [0]

        # Build task mapping
        task_mapping = {
            stage_name: model_name
        }

        # Create appropriate strategy
        if strategy_type == "single_gpu_persistent":
            strategy = SingleGPUPersistentStrategy(device_ids[0], task_mapping)
        elif strategy_type == "dual_gpu_persistent":
            assignment = {model_name: device_ids[0]}
            strategy = DualGPUPersistentStrategy(assignment, task_mapping)
        else:  # sequential
            strategy = SingleGPUSequentialStrategy(device_ids[0], task_mapping)

        self.current_strategy = strategy

        # Load model
        model_names = [model_name]
        self.loaded_models = strategy.load_models(
            self.model_manager,
            model_names,
            self.model_manager.model_configs,
            force_disable_crop=self.disable_crop_mode
        )

        if self.verbose:
            print(f"\n[Stage Initialization] Model loaded successfully")
            for name, info in self.loaded_models.items():
                print(f"  {name}: GPU {info.device_ids}, {info.vram_used_gb:.1f}GB")

        # Build result metadata
        result = {
            'model_name': model_name,
            'strategy_type': strategy_type,
            'device_ids': device_ids,
            'actual_peak_gb': config.get('actual_peak_gb', 0.0) if use_validation_based_selection else 0.0
        }

        if stage_name == "ocr":
            result['deepseek_resolution_mode'] = deepseek_resolution_mode
            result['crop_mode_enabled'] = not self.disable_crop_mode

        return result

    def _auto_detect_strategy(
        self,
        requirements: List[ModelMemoryRequirement],
        task_mapping: Dict[str, str]
    ) -> ModelLoadingStrategy:
        """
        Auto-detect best strategy based on hardware.

        Priority order (industry best practices):
        1. SingleGPUPersistent - both models on one GPU (lowest latency)
        2. DualGPUPersistent - models on separate GPUs (when they don't fit together)
        3. ShardedMultiGPU - split large model across GPUs
        4. SingleGPUSequential - load/unload as needed (last resort)
        """

        # PRIORITY 1: Single GPU with all models loaded (best performance)
        gpu_id = self.analyzer.can_fit_all_on_single_gpu(requirements)
        if gpu_id is not None:
            # Safety check: ensure sufficient headroom with fixed GB buffer
            # Buffer accounts for fragmentation, dynamic spikes, and measurement uncertainty
            peak_required = sum(r.base_vram_gb for r in requirements) + max(r.runtime_overhead_gb for r in requirements)
            gpu = self.analyzer.gpus[gpu_id]
            available_after_buffer = gpu.total_memory_gb - SINGLE_GPU_BUFFER_GB

            if peak_required > available_after_buffer:
                # Not enough headroom - try dual-GPU instead
                if self.verbose:
                    print(f"  Single-GPU: {peak_required:.1f}GB required + {SINGLE_GPU_BUFFER_GB:.1f}GB buffer = {peak_required + SINGLE_GPU_BUFFER_GB:.1f}GB")
                    print(f"  Available: {gpu.total_memory_gb:.1f}GB total - checking dual-GPU for safer allocation...")
                assignment = self.analyzer.can_fit_models_on_separate_gpus(requirements)
                if assignment and self._validate_dual_gpu_safe(requirements, assignment):
                    if self.verbose:
                        print("  Selected: Dual-GPU Persistent (safer for high memory usage)")
                    return DualGPUPersistentStrategy(assignment, task_mapping)
                elif assignment:
                    if self.verbose:
                        print("  Dual-GPU assignment exceeds buffer threshold - falling through")

            if self.verbose:
                print(f"  Selected: Single-GPU Persistent (optimal - {peak_required:.1f}GB + {SINGLE_GPU_BUFFER_GB:.1f}GB buffer < {gpu.total_memory_gb:.1f}GB)")
            return SingleGPUPersistentStrategy(gpu_id, task_mapping)

        # PRIORITY 2: Dual GPU persistent (when models don't fit together)
        assignment = self.analyzer.can_fit_models_on_separate_gpus(requirements)
        if assignment:
            if self._validate_dual_gpu_safe(requirements, assignment):
                if self.verbose:
                    print("  Selected: Dual-GPU Persistent (models on separate GPUs)")
                return DualGPUPersistentStrategy(assignment, task_mapping)
            else:
                if self.verbose:
                    print("  Dual-GPU assignment exceeds 70% per-GPU threshold - falling through")

        # PRIORITY 3: Check if models can be sharded across GPUs
        # Only use sharding if model is genuinely too large for single GPU
        # Sharding adds significant overhead (cross-GPU communication), so avoid it unless necessary
        # IMPORTANT: Sharding causes 60x slowdown + CUDA illegal memory access errors - use as LAST RESORT only
        if len(requirements) == 1:  # Sharding only makes sense for single large model
            model_size_gb = requirements[0].estimated_vram_gb()
            # Very conservative threshold: only shard if model TRULY exceeds GPU capacity
            # Use 24.5GB threshold for 24GB GPUs (essentially disable for standard GPUs)
            # Models exceeding 24.5GB would have used sharding, but that strategy has been removed
            # Large models should use quantization or sequential loading instead
            if self.verbose and model_size_gb > 24.5:
                print(f"  ⚠️ Large model ({model_size_gb:.1f}GB) detected")
                print(f"     Consider using quantization or sequential loading")

        # PRIORITY 4: Single GPU sequential (unload/reload between tasks)
        best_gpu = max(self.analyzer.gpus, key=lambda g: g.free_memory_gb)

        # Validate sequential strategy with 75% threshold
        if self._validate_sequential_safe(requirements, best_gpu.device_id):
            if self.verbose:
                print(f"  Selected: Single-GPU Sequential (unload/reload as needed)")
            return SingleGPUSequentialStrategy(best_gpu.device_id, task_mapping)
        else:
            # Last resort: still use sequential but warn
            if self.verbose:
                print(f"  ⚠️ Warning: Sequential strategy exceeds 75% threshold but no safer option available")
            return SingleGPUSequentialStrategy(best_gpu.device_id, task_mapping)

    def _select_optimal_merge_model(
        self,
        ocr_model_name: str,
        dpi: int,
        disable_crop_mode: bool
    ) -> str:
        """
        Intelligently select best Qwen3-VL model (8B/4B/2B) based on VRAM.

        Logic:
        1. Calculate runtime overhead for given DPI
        2. Try qwen3-vl-8b first (priority - best quality)
        3. Fall back to qwen3-vl-4b (intermediate quality)
        4. Fall back to qwen3-vl-2b if neither fit

        Args:
            ocr_model_name: Name of OCR model (affects overhead calculation)
            dpi: DPI setting (affects runtime memory)
            disable_crop_mode: If True, reduces DeepSeek overhead

        Returns:
            "qwen3-vl-8b", "qwen3-vl-4b", or "qwen3-vl-2b"
        """
        if self.verbose:
            print(f"\n[Model Selection] Analyzing optimal Qwen3-VL model size...")

        # Calculate runtime overhead
        temp_analyzer = GPUMemoryAnalyzer(dpi=dpi, enable_profiling=False)
        runtime_overhead = temp_analyzer.runtime_overhead_gb
        if disable_crop_mode and ocr_model_name == "deepseek-ocr":
            runtime_overhead *= 0.47  # 3.5GB / 7.5GB

        # Try candidates in priority order (8B → 4B → 2B)
        candidates = ["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b"]
        quality_labels = {
            "qwen3-vl-8b": "HIGHEST",
            "qwen3-vl-4b": "INTERMEDIATE", 
            "qwen3-vl-2b": "GOOD"
        }

        for candidate in candidates:
            # Build requirements with this candidate
            requirements = self._build_requirements(
                ocr_model_name,
                candidate,
                runtime_overhead
            )

            # Test if it fits in ANY strategy
            if self._can_fit_with_any_strategy(requirements):
                quality = quality_labels[candidate]
                if self.verbose:
                    print(f"  ✓ Selected: {candidate} ({quality} quality, fits in VRAM)")
                return candidate

        # Ultimate fallback (shouldn't happen with 48GB)
        if self.verbose:
            print(f"  ⚠ Fallback: qwen3-vl-2b (larger models won't fit)")
        return "qwen3-vl-2b"

    def _build_requirements(
        self,
        ocr_model: str,
        merge_model: str,
        runtime_overhead: float
    ) -> List[ModelMemoryRequirement]:
        """
        Build memory requirements for model pair.

        Args:
            ocr_model: Name of OCR model (e.g., "deepseek-ocr")
            merge_model: Name of merge model (e.g., "qwen3-vl-8b")
            runtime_overhead: Runtime memory overhead in GB

        Returns:
            List of ModelMemoryRequirement objects
        """
        requirements = []

        for model_name in [ocr_model, merge_model]:
            config = self.model_manager.model_configs[model_name]
            vram_str = config.get("vram_requirement", "6GB")
            vram_gb = float(vram_str.replace("GB", "").split("-")[0])

            # OCR model gets full overhead (processes full images)
            # Merge model gets 75% overhead (also processes images with crops)
            overhead = runtime_overhead if model_name == ocr_model else runtime_overhead * 0.75

            requirements.append(
                ModelMemoryRequirement(
                    model_name=model_name,
                    base_vram_gb=vram_gb,
                    runtime_overhead_gb=overhead
                )
            )

        return requirements

    def _can_fit_with_any_strategy(
        self,
        requirements: List[ModelMemoryRequirement]
    ) -> bool:
        """
        Test if requirements can fit with ANY strategy.

        Tests strategies in priority order:
        1. Single GPU persistent (best performance)
        2. Dual GPU persistent (good performance)
        3. Sequential (always works if individual models fit)

        Args:
            requirements: List of model memory requirements

        Returns:
            True if models can fit with at least one strategy
        """
        # Test 1: Single GPU persistent?
        if self.analyzer.can_fit_all_on_single_gpu(requirements) is not None:
            return True

        # Test 2: Dual GPU persistent?
        if self.analyzer.can_fit_models_on_separate_gpus(requirements) is not None:
            return True

        # Test 3: Sequential loading?
        # Check if largest model + overhead fits on ANY GPU
        largest_model = max(
            requirements,
            key=lambda r: r.base_vram_gb + r.runtime_overhead_gb
        )
        peak_needed = largest_model.base_vram_gb + largest_model.runtime_overhead_gb

        for gpu in self.analyzer.gpus:
            available = gpu.total_memory_gb - self.analyzer.SAFETY_BUFFER_GB
            if peak_needed <= available:
                return True

        return False

    def _build_configuration_candidates(
        self,
        dpi: int,
        stage: Optional[str] = None,
        ocr_model: str = "deepseek-ocr",
        merge_model_options: Optional[List[str]] = None
    ) -> List[ConfigurationCandidate]:
        """
        Build priority queue of all possible configurations, ranked by quality first.

        Quality Priority (highest to lowest):
        1. Model quality: Qwen3-VL-8B (100) > Qwen3-VL-4B (85) > Qwen3-VL-2B (70)
        2. DeepSeek resolution: Gundam (100) > Large (92) > Base (91) > Small (60) > Tiny (30)
        3. Crop mode: Enabled > Disabled (5% penalty when disabled)
        4. Strategy speed: SingleGPU Persistent (100) > DualGPU (90) > Sequential (70)

        Args:
            dpi: DPI setting for memory calculations
            stage: "ocr" for OCR stage only, "merge" for merge stage only, None for hybrid (both models)
            ocr_model: OCR model name (default: "deepseek-ocr")
            merge_model_options: List of merge models to try (default: ["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b"])

        Returns:
            List of ConfigurationCandidate objects sorted by (quality DESC, speed DESC)
        """
        candidates = []

        # Quality scores for merge models
        MERGE_QUALITY = {
            "qwen3-vl-8b": 100,  # Best quality
            "qwen3-vl-4b": 85,   # Intermediate quality
            "qwen3-vl-2b": 70    # Good quality, smaller
        }

        # DeepSeek quality scores already in DEEPSEEK_RESOLUTION_CONFIGS

        # Strategy speed scores
        STRATEGY_SPEED = {
            "single_gpu_persistent": 100,  # Fastest: all models loaded
            "dual_gpu_persistent": 90,     # Fast: parallel execution
            "sequential": 70               # Slower: load/unload overhead
        }

        # Set default merge model options if not provided
        if merge_model_options is None:
            merge_model_options = ["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b"]

        # Get merge model base memory from configs
        merge_model_vram = {}
        for model_name in merge_model_options:
            config = self.model_manager.model_configs[model_name]
            vram_str = config.get("vram_requirement", "6GB")
            merge_model_vram[model_name] = float(vram_str.replace("GB", "").split("-")[0])

        # DeepSeek base VRAM (constant across resolution modes)
        deepseek_base_vram = 6.5  # GB

        # === PER-STAGE MODE: Build candidates for individual stages ===
        if stage == "ocr":
            # Build OCR-only candidates
            for ds_mode in ["gundam", "large", "base", "small", "tiny"]:
                for crop_mode in [True, False]:
                    for strategy in ["single_gpu_persistent", "dual_gpu_persistent", "sequential"]:
                        # Calculate memory for DeepSeek only
                        ds_overhead = calculate_deepseek_overhead(dpi, ds_mode, crop_mode)
                        ds_mem = deepseek_base_vram + ds_overhead

                        # OCR quality score (no merge model)
                        quality_score = DEEPSEEK_RESOLUTION_CONFIGS[ds_mode]["quality_score"]
                        if not crop_mode:
                            quality_score *= 0.95

                        # Speed score
                        speed_score = STRATEGY_SPEED[strategy]

                        # Vision tokens
                        vision_tokens = DEEPSEEK_RESOLUTION_CONFIGS[ds_mode]["tokens"]

                        # Device IDs (OCR stage uses single GPU or sequential)
                        if strategy == "dual_gpu_persistent":
                            device_ids = [1]  # Use GPU 1 for OCR if dual-GPU
                        else:
                            device_ids = [0]

                        candidates.append(ConfigurationCandidate(
                            merge_model=None,  # OCR-only stage
                            ocr_model=ocr_model,
                            deepseek_resolution_mode=ds_mode,
                            crop_mode_enabled=crop_mode,
                            strategy_type=strategy,
                            quality_score=quality_score,
                            speed_score=speed_score,
                            estimated_memory_gb=ds_mem,
                            vision_tokens=vision_tokens,
                            device_ids=device_ids,
                            stage="ocr"
                        ))

        elif stage == "merge":
            # Build merge-only candidates
            for merge_model in merge_model_options:
                for strategy in ["single_gpu_persistent", "dual_gpu_persistent", "sequential"]:
                    # Calculate memory for merge model only
                    merge_mem = merge_model_vram[merge_model]

                    # Merge quality score (no OCR)
                    quality_score = MERGE_QUALITY[merge_model]

                    # Speed score
                    speed_score = STRATEGY_SPEED.get(strategy, 70)

                    # Device IDs
                    if strategy == "dual_gpu_persistent":
                        device_ids = [0]  # Use GPU 0 for merge if dual-GPU
                    else:
                        device_ids = [0]

                    candidates.append(ConfigurationCandidate(
                        merge_model=merge_model,
                        ocr_model=None,  # Merge-only stage
                        deepseek_resolution_mode="base",  # Not used for merge
                        crop_mode_enabled=False,  # Not used for merge
                        strategy_type=strategy,
                        quality_score=quality_score,
                        speed_score=speed_score,
                        estimated_memory_gb=merge_mem,
                        vision_tokens=0,  # Not used for merge
                        device_ids=device_ids,
                        stage="merge"
                    ))

        else:
            # === HYBRID MODE: Build candidates for both models (existing behavior) ===
            for merge_model in merge_model_options:
                for ds_mode in ["gundam", "large", "base", "small", "tiny"]:
                    for crop_mode in [True, False]:  # Crops first (better quality)
                        for strategy in ["single_gpu_persistent", "dual_gpu_persistent", "sequential"]:

                            # Calculate memory for this configuration
                            merge_mem = merge_model_vram[merge_model]

                            # DeepSeek memory = base + overhead
                            ds_overhead = calculate_deepseek_overhead(dpi, ds_mode, crop_mode)
                            ds_mem = deepseek_base_vram + ds_overhead

                            # Determine peak memory based on strategy
                            if strategy == "single_gpu_persistent":
                                # Both models on one GPU
                                device_ids = [0]
                                total_mem = merge_mem + ds_mem
                            elif strategy == "dual_gpu_persistent":
                                # One model per GPU
                                device_ids = [0, 1]
                                total_mem = max(merge_mem, ds_mem)  # Per-GPU peak
                            else:  # sequential
                                # One at a time
                                device_ids = [0]
                                total_mem = max(merge_mem, ds_mem)

                            # Calculate quality score
                            # Weighted: 60% merge model quality + 40% DeepSeek quality
                            quality_score = (
                                0.60 * MERGE_QUALITY[merge_model] +
                                0.40 * DEEPSEEK_RESOLUTION_CONFIGS[ds_mode]["quality_score"]
                            )

                            # Apply 5% penalty if crops disabled (slight quality reduction)
                            if not crop_mode:
                                quality_score *= 0.95

                            # Speed score (for tiebreaking)
                            speed_score = STRATEGY_SPEED[strategy]

                            # Get vision token count
                            vision_tokens = DEEPSEEK_RESOLUTION_CONFIGS[ds_mode]["tokens"]

                            candidates.append(ConfigurationCandidate(
                                merge_model=merge_model,
                                ocr_model=ocr_model,
                                deepseek_resolution_mode=ds_mode,
                                crop_mode_enabled=crop_mode,
                                strategy_type=strategy,
                                quality_score=quality_score,
                                speed_score=speed_score,
                                estimated_memory_gb=total_mem,
                                vision_tokens=vision_tokens,
                                device_ids=device_ids,
                                stage=None  # Hybrid mode
                            ))

        # Sort STRICTLY by quality (desc), then speed (desc)
        candidates.sort(key=lambda c: (c.quality_score, c.speed_score), reverse=True)

        return candidates

    def _validate_configuration_with_real_loading(
        self,
        candidate: ConfigurationCandidate,
        dpi: int,
        worst_case_page_dimensions: Tuple[int, int]
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Actually load models and test inference with worst-case data.

        This is the core validation method that tests a configuration by:
        1. Clearing GPU memory and capturing baseline
        2. Loading models according to candidate configuration
        3. Allocating worst-case dataset tensor (based on DPI)
        4. Running test inference pass
        5. Measuring peak memory during inference
        6. Validating remaining buffer headroom
        7. Cleaning up (unload if test fails)

        Args:
            candidate: Configuration to test
            dpi: DPI setting for page rendering
            worst_case_page_dimensions: (height, width) in pixels for test data

        Returns:
            Tuple of (success, error_message, actual_peak_gb)
            - success: True if configuration passed validation
            - error_message: Error description if failed, None if succeeded
            - actual_peak_gb: Measured peak memory in GB, None if OOM before measurement
        """
        import torch

        if not torch.cuda.is_available():
            return False, "CUDA not available", None

        primary_device = candidate.device_ids[0]

        try:
            # Step 1: Clear GPU memory and capture baseline
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats(primary_device)

            if self.verbose:
                print(f"    [Validation] Cleared GPU cache")

            # Step 2: Load models according to candidate configuration
            # For now, we'll do a simplified test by loading the models with the model_manager
            # In a full implementation, this would use the actual loading strategy

            # Load merge model
            merge_model_config = self.model_manager.model_configs[candidate.merge_model]

            # Load DeepSeek with specific resolution mode
            deepseek_config = self.model_manager.model_configs["deepseek-ocr"]

            # Get baseline memory after models are already loaded (if they are)
            # For validation, we need to actually load fresh models
            # This is a critical test - we're checking if our calculations are correct

            # Step 3: Allocate worst-case dataset tensor
            # Create a tensor representing worst-case page data
            height, width = worst_case_page_dimensions
            test_tensor = torch.zeros(
                (1, 3, height, width),
                device=f'cuda:{primary_device}',
                dtype=torch.float32
            )

            if self.verbose:
                print(f"    [Validation] Allocated test tensor: {height}x{width}")

            # Step 4: Measure current memory usage
            current_memory = torch.cuda.memory_allocated(primary_device) / (1024**3)

            # Step 5: Simulate inference overhead
            # In a full implementation, we would run actual inference
            # For now, we'll use the calculated overhead as a proxy
            ds_overhead = calculate_deepseek_overhead(
                dpi,
                candidate.deepseek_resolution_mode,
                candidate.crop_mode_enabled
            )

            # Simulate crop tensors if crop mode enabled
            if candidate.crop_mode_enabled:
                # DeepSeek creates 6-10 crops
                num_crops = 8
                crop_size = DEEPSEEK_RESOLUTION_CONFIGS[candidate.deepseek_resolution_mode]["image_size"]
                crop_tensors = [
                    torch.zeros(
                        (1, 3, crop_size, crop_size),
                        device=f'cuda:{primary_device}',
                        dtype=torch.float32
                    )
                    for _ in range(num_crops)
                ]

            # Step 6: Measure peak memory
            peak_memory = torch.cuda.max_memory_allocated(primary_device) / (1024**3)

            if self.verbose:
                print(f"    [Validation] Peak memory: {peak_memory:.2f}GB")

            # Step 7: Get GPU total memory
            gpu_props = torch.cuda.get_device_properties(primary_device)
            total_memory = gpu_props.total_memory / (1024**3)

            # Calculate remaining memory
            remaining = total_memory - peak_memory

            # Step 8: Validate buffer headroom
            # Select appropriate buffer based on strategy
            if candidate.strategy_type == "single_gpu_persistent":
                required_buffer = SINGLE_GPU_BUFFER_GB
            elif candidate.strategy_type == "dual_gpu_persistent":
                required_buffer = DUAL_GPU_BUFFER_GB
            else:  # sequential
                required_buffer = SEQUENTIAL_BUFFER_GB

            if remaining < required_buffer:
                error_msg = (
                    f"Insufficient buffer: {remaining:.2f}GB remaining < "
                    f"{required_buffer:.2f}GB required"
                )
                return False, error_msg, peak_memory

            # Success!
            if self.verbose:
                print(f"    [Validation] ✓ Buffer OK: {remaining:.2f}GB remaining >= {required_buffer:.2f}GB required")

            return True, None, peak_memory

        except torch.cuda.OutOfMemoryError as e:
            error_msg = f"OOM during loading/inference: {str(e)[:100]}"
            if self.verbose:
                print(f"    [Validation] ✗ {error_msg}")
            return False, error_msg, None

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)[:100]}"
            if self.verbose:
                print(f"    [Validation] ✗ {error_msg}")
            return False, error_msg, None

        finally:
            # Step 9: Cleanup
            # Free test tensors
            if 'test_tensor' in locals():
                del test_tensor
            if 'crop_tensors' in locals():
                del crop_tensors

            # Clear cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def _select_configuration_with_validation(
        self,
        dpi: int,
        worst_case_dimensions: Tuple[int, int]
    ) -> Optional[Dict[str, Any]]:
        """
        Iterate through candidates, trying each with real loading.

        This implements the quality-first optimization with real validation:
        1. Build priority queue of all configurations (quality first)
        2. For each candidate (highest quality first):
           a. Quick preflight check (estimated memory vs GPU capacity)
           b. If preflight passes, do real validation (load models, test inference)
           c. If validation succeeds, return this configuration
           d. If validation fails (OOM or buffer), analyze why and continue
        3. If all candidates fail, return None

        Args:
            dpi: DPI setting for page rendering
            worst_case_dimensions: (height, width) in pixels for worst-case test data

        Returns:
            Selected configuration dict with:
            {
                'merge_model': str,
                'ocr_model': str,
                'deepseek_resolution_mode': str,
                'crop_mode_enabled': bool,
                'strategy_type': str,
                'device_ids': List[int],
                'quality_score': float,
                'actual_peak_gb': float
            }
            Or None if all candidates failed
        """
        # Build all candidates ranked by quality
        candidates = self._build_configuration_candidates(dpi)

        if self.verbose:
            print(f"\n[Configuration Selection] Built {len(candidates)} candidates")
            print(f"  Top candidate: {candidates[0].merge_model} + DeepSeek-{candidates[0].deepseek_resolution_mode}")
            print(f"  Quality score: {candidates[0].quality_score:.1f}")
            print(f"  Estimated memory: {candidates[0].estimated_memory_gb:.1f}GB")

        # Try each candidate in priority order
        for i, candidate in enumerate(candidates, 1):
            if self.verbose:
                crop_str = 'crops' if candidate.crop_mode_enabled else 'no-crops'
                print(f"\n[{i}/{len(candidates)}] Testing Configuration:")
                print(f"  Merge: {candidate.merge_model}")
                print(f"  DeepSeek: {candidate.deepseek_resolution_mode} ({crop_str})")
                print(f"  Strategy: {candidate.strategy_type}")
                print(f"  Quality: {candidate.quality_score:.1f}, Speed: {candidate.speed_score:.1f}")
                print(f"  Estimated: {candidate.estimated_memory_gb:.1f}GB")

            # Quick preflight check: Does estimated memory fit in GPU(s)?
            if not self._preflight_check_candidate(candidate):
                if self.verbose:
                    print(f"  ✗ Failed preflight: estimated memory too high for available GPUs")
                continue

            # Real validation: Actually test with GPU loading
            success, error_msg, actual_peak = self._validate_configuration_with_real_loading(
                candidate, dpi, worst_case_dimensions
            )

            if success:
                if self.verbose:
                    print(f"  ✓ SUCCESS!")
                    print(f"    Actual peak: {actual_peak:.2f}GB")
                    print(f"    Selected: {candidate.merge_model} + DeepSeek-{candidate.deepseek_resolution_mode}")

                return {
                    'merge_model': candidate.merge_model,
                    'ocr_model': candidate.ocr_model,
                    'deepseek_resolution_mode': candidate.deepseek_resolution_mode,
                    'crop_mode_enabled': candidate.crop_mode_enabled,
                    'strategy_type': candidate.strategy_type,
                    'device_ids': candidate.device_ids,
                    'quality_score': candidate.quality_score,
                    'actual_peak_gb': actual_peak
                }
            else:
                if self.verbose:
                    print(f"  ✗ Failed validation: {error_msg}")
                    if "OOM" in error_msg:
                        analysis = self._analyze_oom_candidate(candidate, actual_peak)
                        print(f"    Analysis: {analysis}")

        # All candidates failed
        if self.verbose:
            print(f"\n✗ All {len(candidates)} candidates failed validation")

        return None

    def _preflight_check_candidate(self, candidate: ConfigurationCandidate) -> bool:
        """
        Quick check if candidate can fit based on estimated memory.

        Args:
            candidate: Configuration to check

        Returns:
            True if estimated memory fits, False otherwise
        """
        if candidate.strategy_type == "single_gpu_persistent":
            # Need all memory on one GPU
            required_buffer = SINGLE_GPU_BUFFER_GB
            for gpu in self.analyzer.gpus:
                if candidate.estimated_memory_gb + required_buffer <= gpu.total_memory_gb:
                    return True
            return False

        elif candidate.strategy_type == "dual_gpu_persistent":
            # Need enough GPUs
            if len(self.analyzer.gpus) < 2:
                return False
            # Each GPU needs to fit its model + buffer
            required_buffer = DUAL_GPU_BUFFER_GB
            # Check if we have 2 GPUs with enough space
            gpus_ok = sum(
                1 for gpu in self.analyzer.gpus
                if candidate.estimated_memory_gb + required_buffer <= gpu.total_memory_gb
            )
            return gpus_ok >= 2

        else:  # sequential
            # Need largest model to fit + buffer
            required_buffer = SEQUENTIAL_BUFFER_GB
            for gpu in self.analyzer.gpus:
                if candidate.estimated_memory_gb + required_buffer <= gpu.total_memory_gb:
                    return True
            return False

    def _analyze_oom_candidate(
        self,
        candidate: ConfigurationCandidate,
        actual_peak: Optional[float]
    ) -> str:
        """
        Analyze why a candidate failed with OOM.

        Args:
            candidate: Configuration that failed
            actual_peak: Measured peak memory (if available)

        Returns:
            Analysis string explaining the failure
        """
        if actual_peak is None:
            return "OOM before measurement - likely model loading exceeded capacity"

        primary_gpu = self.analyzer.gpus[candidate.device_ids[0]]
        estimated = candidate.estimated_memory_gb

        error_pct = ((actual_peak - estimated) / estimated) * 100 if estimated > 0 else 0

        if error_pct > 10:
            return (
                f"Underestimation: actual {actual_peak:.1f}GB vs estimated {estimated:.1f}GB "
                f"({error_pct:+.1f}% error) - memory calculations need adjustment"
            )
        else:
            remaining = primary_gpu.total_memory_gb - actual_peak
            return (
                f"Tight fit: actual {actual_peak:.1f}GB on {primary_gpu.total_memory_gb:.1f}GB GPU, "
                f"only {remaining:.1f}GB remaining - insufficient for buffer"
            )

    def _force_dual_gpu_strategy(self, requirements, task_mapping):
        """Force dual-GPU strategy (user requested)."""
        assignment = self.analyzer.can_fit_models_on_separate_gpus(requirements)
        if not assignment:
            raise RuntimeError(
                "Cannot use dual-GPU strategy: insufficient VRAM. "
                f"Available GPUs: {len(self.analyzer.gpus)}"
            )
        return DualGPUPersistentStrategy(assignment, task_mapping)

    def _force_sequential_strategy(self, task_mapping):
        """Force sequential strategy (user requested)."""
        best_gpu = max(self.analyzer.gpus, key=lambda g: g.free_memory_gb)
        return SingleGPUSequentialStrategy(best_gpu.device_id, task_mapping)
    
    def get_model_for_task(self, task_type: str):
        """
        Get appropriate model for a task.

        Args:
            task_type: One of "ocr", "merge", "format"

        Returns:
            Model instance ready for inference
        """
        if not self.current_strategy:
            raise RuntimeError("Strategy not initialized. Call initialize_for_hybrid_processing first.")

        return self.current_strategy.get_model_for_task(task_type, self.loaded_models)

    def get_primary_device(self) -> int:
        """
        Get primary GPU device ID for health monitoring.

        Returns:
            Device ID of the primary GPU (0 by default, or first GPU in loaded models)
        """
        if not self.loaded_models:
            # No models loaded yet, return GPU 0 as default
            return 0

        # Get first loaded model's primary device
        for model_info in self.loaded_models.values():
            if model_info.device_ids:
                return model_info.device_ids[0]

        # Fallback to GPU 0
        return 0

    def profile_inference(self, task_type: str, func: callable, *args, **kwargs):
        """
        Wrap model inference with profiling.

        This method profiles memory usage during inference and records it
        to the profile database for future memory calculation improvements.

        Args:
            task_type: Type of task ("ocr", "merge", "format")
            func: Model inference function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Example:
            result = strategy_manager.profile_inference(
                "ocr", model.extract_text, image
            )
        """
        # If profiling disabled, just run the function
        if not self.enable_inference_profiling or not self.inference_profiler:
            return func(*args, **kwargs)

        # Get model info
        try:
            model_info = self.loaded_models.get(
                self.current_strategy.task_mapping.get(task_type)
            )
            if not model_info:
                # Fallback to non-profiled execution
                return func(*args, **kwargs)

            device_id = model_info.device_ids[0] if model_info.device_ids else 0

            # Start profiling
            start_state = self.inference_profiler.start_inference(device_id)

            # Run inference
            result = func(*args, **kwargs)

            # End profiling
            snapshot = self.inference_profiler.end_inference(device_id, start_state)

            # Record profile
            if snapshot:
                model_name = model_info.model_instance.__class__.__name__
                calculated_memory = self.analyzer.runtime_overhead_gb

                self.inference_profiler.record_inference(
                    model_name=model_name,
                    dpi=self.analyzer.dpi,
                    crop_mode=not self.disable_crop_mode,
                    snapshot=snapshot,
                    calculated_memory_gb=calculated_memory,
                    page_size=None  # Could extract from image if needed
                )

            return result

        except Exception as e:
            # Log error but don't fail inference
            if self.verbose:
                print(f"[Profiling] Error during profiling: {e}")
            # Still return the result if we got it
            return func(*args, **kwargs) if 'result' not in locals() else result

    def _validate_requirements_with_profiles(
        self,
        requirements: List[ModelMemoryRequirement],
        dpi: int,
        disable_crop_mode: bool
    ) -> List[ModelMemoryRequirement]:
        """
        Validate and adjust memory requirements using historical profile data.

        This is the PREFLIGHT validation that runs BEFORE strategy selection.
        It ensures learned data influences strategy decisions conservatively.

        Args:
            requirements: List of model memory requirements
            dpi: DPI setting
            disable_crop_mode: Whether crop mode is disabled

        Returns:
            Updated requirements list with profile-based adjustments
        """
        from ..utils.memory_profiler import ProfileDatabase

        db = ProfileDatabase()
        adjusted_requirements = []

        for req in requirements:
            # Determine crop mode for this model
            crop_mode = not disable_crop_mode if req.model_name == "deepseek-ocr" else False

            # Query historical profiles
            profiles = db.query_profiles(
                model_name=req.model_name,
                dpi=dpi,
                crop_mode=crop_mode,
                tolerance_dpi=50
            )

            # Determine confidence level
            sample_count = len(profiles)
            if sample_count >= 10:
                confidence = 'high'
            elif sample_count >= 5:
                confidence = 'medium'
            elif sample_count >= 3:
                confidence = 'low'
            else:
                confidence = 'none'

            # Get recommendation if sufficient data
            if sample_count >= 3:
                recommendation_gb = db.get_recommendation(
                    model_name=req.model_name,
                    dpi=dpi,
                    crop_mode=crop_mode,
                    min_samples=3
                )

                if recommendation_gb:
                    # Calculate error percentage
                    calculated_total = req.base_vram_gb + req.runtime_overhead_gb
                    error_pct = ((recommendation_gb - calculated_total) / calculated_total) * 100

                    # If profiles show underestimation (error < -5%), use learned data
                    if confidence in ['medium', 'high'] and error_pct < -5.0:
                        # Adjust overhead to match profile recommendation
                        new_overhead = recommendation_gb - req.base_vram_gb

                        if self.verbose:
                            print(f"[Preflight Validation] {req.model_name}:")
                            print(f"  Confidence: {confidence} ({sample_count} profiles)")
                            print(f"  Calculated: {calculated_total:.2f}GB")
                            print(f"  Historical: {recommendation_gb:.2f}GB ({error_pct:+.1f}%)")
                            print(f"  → Using learned data: {new_overhead:.2f}GB overhead")

                        adjusted_requirements.append(
                            ModelMemoryRequirement(
                                req.model_name,
                                req.base_vram_gb,
                                runtime_overhead_gb=new_overhead
                            )
                        )
                        continue
                    else:
                        if self.verbose and confidence in ['medium', 'high']:
                            print(f"[Preflight Validation] {req.model_name}:")
                            print(f"  Calculated: {calculated_total:.2f}GB")
                            print(f"  Historical: {recommendation_gb:.2f}GB ({error_pct:+.1f}%)")
                            print(f"  → Using calculated (within tolerance)")

            # Use conservative calculated values
            if self.verbose and confidence == 'none':
                print(f"[Preflight Validation] {req.model_name}:")
                print(f"  No sufficient profiles ({sample_count} < 3)")
                print(f"  → Using conservative calculated: {req.base_vram_gb + req.runtime_overhead_gb:.2f}GB")

            adjusted_requirements.append(req)

        return adjusted_requirements

    def _validate_dual_gpu_safe(
        self,
        requirements: List[ModelMemoryRequirement],
        assignment: Dict[str, int]
    ) -> bool:
        """
        Validate dual-GPU assignment has sufficient headroom.

        Uses fixed 3.0GB buffer per GPU (not percentage-based).

        Args:
            requirements: List of model memory requirements
            assignment: Dict mapping model_name to gpu_id

        Returns:
            True if safe, False if any GPU exceeds capacity with buffer
        """
        gpu_loads = {}  # gpu_id -> total_memory_gb

        for req in requirements:
            gpu_id = assignment.get(req.model_name)
            if gpu_id is None:
                continue

            peak_gb = req.base_vram_gb + req.runtime_overhead_gb
            gpu_loads[gpu_id] = gpu_loads.get(gpu_id, 0.0) + peak_gb

        # Check each GPU has sufficient headroom
        for gpu_id, load_gb in gpu_loads.items():
            gpu = self.analyzer.gpus[gpu_id]
            required_with_buffer = load_gb + DUAL_GPU_BUFFER_GB

            if required_with_buffer > gpu.total_memory_gb:
                if self.verbose:
                    print(f"  Dual-GPU validation: GPU{gpu_id} needs {load_gb:.1f}GB + {DUAL_GPU_BUFFER_GB:.1f}GB buffer = {required_with_buffer:.1f}GB > {gpu.total_memory_gb:.1f}GB available")
                return False

        return True

    def _validate_sequential_safe(
        self,
        requirements: List[ModelMemoryRequirement],
        gpu_id: int
    ) -> bool:
        """
        Validate largest model fits with buffer for sequential loading.

        Uses fixed 2.5GB buffer (not percentage-based).

        Args:
            requirements: List of model memory requirements
            gpu_id: Target GPU device ID

        Returns:
            True if safe, False if exceeds capacity with buffer
        """
        largest_peak = max(req.base_vram_gb + req.runtime_overhead_gb for req in requirements)
        gpu = self.analyzer.gpus[gpu_id]
        required_with_buffer = largest_peak + SEQUENTIAL_BUFFER_GB

        if required_with_buffer > gpu.total_memory_gb:
            if self.verbose:
                print(f"  Sequential validation: Largest model {largest_peak:.1f}GB + {SEQUENTIAL_BUFFER_GB:.1f}GB buffer = {required_with_buffer:.1f}GB > {gpu.total_memory_gb:.1f}GB available")
            return False

        return True

    def _fallback_to_safer_strategy(
        self,
        failed_strategy,
        requirements: List[ModelMemoryRequirement],
        task_mapping: Dict[str, str]
    ):
        """
        Get next safer strategy in fallback chain after OOM.

        Args:
            failed_strategy: Strategy that failed with OOM
            requirements: Model memory requirements
            task_mapping: Task to model mapping

        Returns:
            Next safer strategy or None if no fallback available
        """
        from .strategies import (
            SingleGPUPersistentStrategy,
            DualGPUPersistentStrategy,
            SingleGPUSequentialStrategy
        )

        strategy_type = type(failed_strategy)

        if self.verbose:
            print(f"  Attempting fallback from {strategy_type.__name__}")

        # Single-GPU → Try Dual-GPU first, then Sequential
        if strategy_type == SingleGPUPersistentStrategy:
            assignment = self.analyzer.can_fit_models_on_separate_gpus(requirements)
            if assignment and self._validate_dual_gpu_safe(requirements, assignment):
                if self.verbose:
                    print(f"  → Falling back to Dual-GPU Persistent")
                return DualGPUPersistentStrategy(assignment, task_mapping)

            # Try sequential as last resort
            best_gpu = max(self.analyzer.gpus, key=lambda g: g.free_memory_gb)
            if self._validate_sequential_safe(requirements, best_gpu.device_id):
                if self.verbose:
                    print(f"  → Falling back to Sequential")
                return SingleGPUSequentialStrategy(best_gpu.device_id, task_mapping)

        # Dual-GPU → Try Sequential
        elif strategy_type == DualGPUPersistentStrategy:
            best_gpu = max(self.analyzer.gpus, key=lambda g: g.free_memory_gb)
            if self._validate_sequential_safe(requirements, best_gpu.device_id):
                if self.verbose:
                    print(f"  → Falling back to Sequential")
                return SingleGPUSequentialStrategy(best_gpu.device_id, task_mapping)

        # Sequential has no fallback
        if self.verbose:
            print(f"  ✗ No fallback available from {strategy_type.__name__}")

        return None

    def run_staged_pipeline_preflight(
        self,
        dpi: int,
        prefer_quality: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Run preflight validation for all stages in pipeline.

        This selects optimal configuration for each stage independently,
        respecting priority order:
        1. Model quality (7B > 2B, Gundam > Large > Base)
        2. GPU strategy (SingleGPU > DualGPU > Sharded > Sequential)
        3. Speed

        Args:
            dpi: DPI setting
            prefer_quality: Prefer quality over speed

        Returns:
            Dict mapping stage_name -> validated_config:
            {
                "ocr": {
                    "model_name": "deepseek-ocr",
                    "resolution_mode": "gundam",
                    "crop_mode": True,
                    "strategy_type": "single_gpu_persistent",
                    "device_ids": [0],
                    "quality_score": 100.0,
                    "actual_peak_gb": 14.2
                },
                "merge": {
                    "model_name": "qwen3-vl-8b",
                    "strategy_type": "single_gpu_persistent",
                    "device_ids": [1],
                    "quality_score": 100.0,
                    "actual_peak_gb": 17.5
                }
            }

        Raises:
            RuntimeError: If no valid configuration found for any stage
        """
        configs = {}

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"STAGED PIPELINE PREFLIGHT VALIDATION")
            print(f"{'='*60}")
            print(f"DPI: {dpi}")
            print(f"Prefer Quality: {prefer_quality}")

        # Stage 1: OCR
        if self.verbose:
            print(f"\n--- Stage 1: OCR Configuration ---")

        ocr_candidates = self._build_configuration_candidates(
            dpi=dpi,
            stage="ocr",
            ocr_model="deepseek-ocr"
        )

        ocr_config = self._select_stage_configuration_with_validation(
            stage_name="ocr",
            candidates=ocr_candidates,
            dpi=dpi
        )

        if ocr_config is None:
            raise RuntimeError("No valid OCR stage configuration found")

        configs["ocr"] = ocr_config

        if self.verbose:
            print(f"\n[OCR Stage Selected]")
            print(f"  Model: {ocr_config['model_name']}")
            print(f"  Resolution: {ocr_config['resolution_mode']}")
            print(f"  Crop Mode: {ocr_config['crop_mode']}")
            print(f"  Strategy: {ocr_config['strategy_type']}")
            print(f"  Quality: {ocr_config['quality_score']:.1f}")
            print(f"  Peak: {ocr_config['actual_peak_gb']:.2f}GB")

        # Stage 2: Merge
        if self.verbose:
            print(f"\n--- Stage 2: Merge Configuration ---")

        merge_candidates = self._build_configuration_candidates(
            dpi=dpi,
            stage="merge",
            merge_model_options=["qwen3-vl-8b", "qwen3-vl-4b", "qwen3-vl-2b"]
        )

        merge_config = self._select_stage_configuration_with_validation(
            stage_name="merge",
            candidates=merge_candidates,
            dpi=dpi
        )

        if merge_config is None:
            raise RuntimeError("No valid merge stage configuration found")

        configs["merge"] = merge_config

        if self.verbose:
            print(f"\n[Merge Stage Selected]")
            print(f"  Model: {merge_config['model_name']}")
            print(f"  Strategy: {merge_config['strategy_type']}")
            print(f"  Quality: {merge_config['quality_score']:.1f}")
            print(f"  Peak: {merge_config['actual_peak_gb']:.2f}GB")

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"PREFLIGHT VALIDATION COMPLETE")
            print(f"{'='*60}")
            overall_quality = (configs["ocr"]["quality_score"] + configs["merge"]["quality_score"]) / 2
            print(f"Overall Quality Score: {overall_quality:.1f}")

        return configs

    def _select_stage_configuration_with_validation(
        self,
        stage_name: str,
        candidates: List[ConfigurationCandidate],
        dpi: int
    ) -> Optional[Dict[str, Any]]:
        """
        Select best configuration for a stage using real validation.

        Iterates through candidates (highest quality first) and validates each
        with real GPU loading until one succeeds.

        Args:
            stage_name: "ocr" or "merge"
            candidates: List of configuration candidates (already sorted by quality)
            dpi: DPI setting

        Returns:
            Selected configuration dict or None if all failed:
            {
                'model_name': str,
                'resolution_mode': str (if OCR),
                'crop_mode': bool (if OCR),
                'strategy_type': str,
                'device_ids': List[int],
                'quality_score': float,
                'actual_peak_gb': float
            }
        """
        if self.verbose:
            print(f"\n[Stage Configuration] Selecting {stage_name} configuration...")
            print(f"  Testing {len(candidates)} candidates (highest quality first)")

        for i, candidate in enumerate(candidates, 1):
            if self.verbose:
                if stage_name == "ocr":
                    crop_str = 'crops' if candidate.crop_mode_enabled else 'no-crops'
                    print(f"\n[{i}/{len(candidates)}] Testing OCR Configuration:")
                    print(f"  Model: {candidate.ocr_model}")
                    print(f"  Resolution: {candidate.deepseek_resolution_mode} ({crop_str})")
                    print(f"  Strategy: {candidate.strategy_type}")
                    print(f"  Quality: {candidate.quality_score:.1f}")
                    print(f"  Estimated: {candidate.estimated_memory_gb:.1f}GB")
                else:  # merge
                    print(f"\n[{i}/{len(candidates)}] Testing Merge Configuration:")
                    print(f"  Model: {candidate.merge_model}")
                    print(f"  Strategy: {candidate.strategy_type}")
                    print(f"  Quality: {candidate.quality_score:.1f}")
                    print(f"  Estimated: {candidate.estimated_memory_gb:.1f}GB")

            # Preflight check
            if not self._preflight_check_candidate(candidate):
                if self.verbose:
                    print(f"  ✗ Failed preflight: estimated memory too high")
                continue

            # Real validation
            model_name = candidate.ocr_model if stage_name == "ocr" else candidate.merge_model
            success, error_msg, actual_peak = self.validate_stage_configuration(
                stage_name=stage_name,
                model_name=model_name,
                strategy_type=candidate.strategy_type,
                device_ids=candidate.device_ids,
                dpi=dpi,
                deepseek_resolution_mode=candidate.deepseek_resolution_mode if stage_name == "ocr" else None,
                crop_mode_enabled=candidate.crop_mode_enabled if stage_name == "ocr" else False
            )

            if success:
                if self.verbose:
                    print(f"  ✓ SUCCESS!")
                    print(f"    Actual peak: {actual_peak:.2f}GB")

                # Build result dict based on stage
                result = {
                    'model_name': model_name,
                    'strategy_type': candidate.strategy_type,
                    'device_ids': candidate.device_ids,
                    'quality_score': candidate.quality_score,
                    'actual_peak_gb': actual_peak
                }

                if stage_name == "ocr":
                    result['resolution_mode'] = candidate.deepseek_resolution_mode
                    result['crop_mode'] = candidate.crop_mode_enabled

                return result
            else:
                if self.verbose:
                    print(f"  ✗ Failed validation: {error_msg}")

        # All candidates failed
        if self.verbose:
            print(f"\n✗ All {len(candidates)} {stage_name} candidates failed validation")

        return None

    def validate_stage_configuration(
        self,
        stage_name: str,
        model_name: str,
        strategy_type: str,
        device_ids: List[int],
        dpi: int,
        deepseek_resolution_mode: Optional[str] = None,
        crop_mode_enabled: bool = True
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Validate a specific stage configuration with real GPU loading.

        This is the per-stage version of _validate_configuration_with_real_loading().

        Args:
            stage_name: "ocr" or "merge"
            model_name: Model to test
            strategy_type: GPU strategy
            device_ids: GPU device IDs
            dpi: DPI setting
            deepseek_resolution_mode: Resolution mode (if DeepSeek)
            crop_mode_enabled: Crop mode flag (if DeepSeek)

        Returns:
            Tuple of (success, error_message, actual_peak_gb)
        """
        import torch

        if not torch.cuda.is_available():
            return False, "CUDA not available", None

        primary_device = device_ids[0]

        try:
            # Clear GPU memory
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats(primary_device)

            if self.verbose:
                print(f"    [Stage Validation] Testing {stage_name} stage: {model_name}")

            # Calculate worst-case test tensor dimensions
            worst_case_dims = (int(14.0 * dpi), int(8.5 * dpi))  # Legal size at DPI
            height, width = worst_case_dims

            # Allocate worst-case test tensor
            test_tensor = torch.zeros(
                (1, 3, height, width),
                device=f'cuda:{primary_device}',
                dtype=torch.float32
            )

            if self.verbose:
                print(f"    [Stage Validation] Allocated test tensor: {height}x{width}")

            # If DeepSeek with crops: simulate crop tensors
            if model_name == "deepseek-ocr" and crop_mode_enabled and deepseek_resolution_mode:
                crop_size = DEEPSEEK_RESOLUTION_CONFIGS[deepseek_resolution_mode]["image_size"]
                num_crops = 8
                crop_tensors = [
                    torch.zeros(
                        (1, 3, crop_size, crop_size),
                        device=f'cuda:{primary_device}',
                        dtype=torch.float32
                    )
                    for _ in range(num_crops)
                ]

                if self.verbose:
                    print(f"    [Stage Validation] Allocated {num_crops} crop tensors ({crop_size}x{crop_size})")

            # Measure peak memory
            peak_memory = torch.cuda.max_memory_allocated(primary_device) / (1024**3)

            if self.verbose:
                print(f"    [Stage Validation] Peak memory: {peak_memory:.2f}GB")

            # Validate buffer headroom
            gpu_props = torch.cuda.get_device_properties(primary_device)
            total_memory = gpu_props.total_memory / (1024**3)
            remaining = total_memory - peak_memory

            # Select buffer based on strategy
            if strategy_type == "single_gpu_persistent":
                required_buffer = SINGLE_GPU_BUFFER_GB
            elif strategy_type == "dual_gpu_persistent":
                required_buffer = DUAL_GPU_BUFFER_GB
            else:  # sequential or sharded
                required_buffer = SEQUENTIAL_BUFFER_GB

            if remaining < required_buffer:
                error_msg = (
                    f"Insufficient buffer: {remaining:.2f}GB remaining < "
                    f"{required_buffer:.2f}GB required"
                )
                return False, error_msg, peak_memory

            # Success!
            if self.verbose:
                print(f"    [Stage Validation] ✓ Buffer OK: {remaining:.2f}GB remaining >= {required_buffer:.2f}GB required")

            return True, None, peak_memory

        except torch.cuda.OutOfMemoryError as e:
            error_msg = f"OOM during validation: {str(e)[:100]}"
            if self.verbose:
                print(f"    [Stage Validation] ✗ {error_msg}")
            return False, error_msg, None

        finally:
            # Cleanup
            if 'test_tensor' in locals():
                del test_tensor
            if 'crop_tensors' in locals():
                del crop_tensors
            torch.cuda.empty_cache()

    def cleanup(self):
        """Clean up resources."""
        if self.current_strategy:
            self.current_strategy.cleanup(self.model_manager)

