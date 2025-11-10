"""GPU memory analysis and detection."""
from dataclasses import dataclass
from typing import List, Dict, Optional
import torch
import psutil  # For system RAM detection
import platform  # For WSL detection


@dataclass
class GPUInfo:
    """Information about a single GPU."""
    device_id: int
    name: str
    total_memory_gb: float
    allocated_memory_gb: float
    free_memory_gb: float
    compute_capability: tuple


@dataclass
class SystemRAMInfo:
    """System RAM information."""
    total_gb: float
    available_gb: float
    used_gb: float
    percent_used: float
    is_wsl: bool  # Whether running on WSL


# DeepSeek-OCR Resolution Mode Configurations
# Based on DeepSeek-OCR paper benchmarks (OmniDocBench)
# Quality scores derived from edit distance measurements
DEEPSEEK_RESOLUTION_CONFIGS = {
    "gundam": {
        "tokens": 795,  # n×640×640 + 1×1024×1024
        "quality_score": 100,  # 0.127 edit distance (best)
        "overhead_multiplier": 2.5,  # Highest memory usage
        "base_size": 1024,
        "image_size": 640
    },
    "large": {
        "tokens": 400,  # 1280×1280
        "quality_score": 92,  # 0.138 edit distance
        "overhead_multiplier": 1.25,
        "base_size": 1280,
        "image_size": 1280
    },
    "base": {
        "tokens": 256,  # 1024×1024
        "quality_score": 91,  # 0.137 edit distance
        "overhead_multiplier": 1.0,  # Baseline
        "base_size": 1024,
        "image_size": 1024
    },
    "small": {
        "tokens": 100,  # 640×640
        "quality_score": 60,  # 0.221 edit distance
        "overhead_multiplier": 0.75,
        "base_size": 640,
        "image_size": 640
    },
    "tiny": {
        "tokens": 64,  # 512×512
        "quality_score": 30,  # 0.386 edit distance (worst)
        "overhead_multiplier": 0.5,  # Lowest memory usage
        "base_size": 512,
        "image_size": 512
    }
}


# Qwen3-VL model memory requirements (FP16)
QWEN3_VL_MEMORY = {
    "qwen3-vl-2b": 4.5,   # ~4-5GB base weights
    "qwen3-vl-4b": 8.5,   # ~8-9GB base weights
    "qwen3-vl-8b": 14.5,  # ~14-15GB base weights
}


def calculate_deepseek_overhead(
    dpi: int,
    resolution_mode: str,
    crop_mode_enabled: bool
) -> float:
    """
    Calculate DeepSeek-OCR memory overhead based on resolution mode.

    Memory overhead varies significantly by resolution mode:
    - Gundam mode: Highest quality, 795 tokens, 2.5x overhead multiplier
    - Large mode: 400 tokens, 1.25x overhead multiplier
    - Base mode: 256 tokens, 1.0x overhead multiplier (baseline)
    - Small mode: 100 tokens, 0.75x overhead multiplier
    - Tiny mode: 64 tokens, 0.5x overhead multiplier

    Crop mode impact (from DeepSeek-OCR paper):
    - With crops: 7.5GB overhead (creates 6-10 crops at multiple resolutions)
    - Without crops: 3.5GB overhead (50% reduction, single resolution)

    Args:
        dpi: DPI setting for page rendering
        resolution_mode: One of "gundam", "large", "base", "small", "tiny"
        crop_mode_enabled: Whether crop mode is enabled

    Returns:
        Estimated memory overhead in GB

    Raises:
        ValueError: If resolution_mode is not recognized
    """
    if resolution_mode not in DEEPSEEK_RESOLUTION_CONFIGS:
        raise ValueError(
            f"Unknown resolution mode '{resolution_mode}'. "
            f"Valid options: {', '.join(DEEPSEEK_RESOLUTION_CONFIGS.keys())}"
        )

    config = DEEPSEEK_RESOLUTION_CONFIGS[resolution_mode]

    # Base overhead depends on crop mode
    if crop_mode_enabled:
        base_overhead = 7.5  # GB with crops (measured from profiling)
    else:
        base_overhead = 3.5  # GB without crops (50% reduction)

    # Scale by resolution mode multiplier
    overhead = base_overhead * config["overhead_multiplier"]

    # DPI scaling: Memory scales quadratically with resolution
    # At 300 DPI (baseline): 1.0x
    # At 600 DPI: 4.0x
    # At 150 DPI: 0.25x
    dpi_factor = (dpi / 300.0) ** 2
    overhead *= dpi_factor

    return overhead


@dataclass
class ModelMemoryRequirement:
    """Memory requirement for a model."""
    model_name: str
    base_vram_gb: float  # From config vram_requirement
    quantization: Optional[str] = None  # None, "int8", "int4"
    runtime_overhead_gb: float = 0.0  # Runtime data (images, activations)

    def estimated_vram_gb(self) -> float:
        """Calculate estimated VRAM with quantization and runtime overhead."""
        model_vram = self.base_vram_gb
        if self.quantization == "int8":
            model_vram = self.base_vram_gb * 0.5
        elif self.quantization == "int4":
            model_vram = self.base_vram_gb * 0.25
        return model_vram + self.runtime_overhead_gb


class GPUMemoryAnalyzer:
    """Analyze GPU memory and determine optimal loading strategy."""
    
    SAFETY_BUFFER_GB = 2.0  # Industry best practice
    
    def __init__(self, dpi: int = 300, enable_profiling: bool = False):
        """
        Initialize GPU memory analyzer.
        
        Args:
            dpi: DPI setting for page rendering (affects image memory)
            enable_profiling: Enable dynamic memory profiling
        """
        self.gpus = self._detect_gpus()
        self.system_ram = self._detect_system_ram()
        self.dpi = dpi
        self.runtime_overhead_gb = self._calculate_runtime_overhead()

        # === NEW: Dynamic profiling ===
        self.enable_profiling = enable_profiling
        self.profiler = None
        
        if enable_profiling:
            self.profiler = MemoryProfiler()
            self._apply_profile_adjustment()
    
    def _apply_profile_adjustment(self) -> None:
        """
        Adjust runtime overhead based on historical profiles.

        If we have enough historical data, use actual measurements
        instead of calculated estimates.
        """
        if not self.enable_profiling or not self.profiler:
            return

        # Try to get adjustment for DeepSeek (most memory intensive)
        adjustment = self.profiler.get_adjustment_factor(
            dpi=self.dpi,
            model_name="deepseek-ocr",
            crop_mode=True
        )

        if adjustment:
            # Use actual measured memory instead of calculated
            old_overhead = self.runtime_overhead_gb
            self.runtime_overhead_gb = adjustment

            print(f"[Memory Profiler] Adjusted overhead: {old_overhead:.2f}GB -> {adjustment:.2f}GB (from historical data)")

    def validate_with_profiles(
        self,
        model_name: str,
        dpi: int,
        crop_mode: bool
    ) -> Dict[str, any]:
        """
        Validate calculated memory against historical profile database.

        Uses the new ProfileDatabase from memory_profiler to compare
        calculated overhead against actual measured values.

        Args:
            model_name: Model to validate
            dpi: DPI setting
            crop_mode: Whether crop mode is enabled

        Returns:
            Dictionary with validation results:
            {
                'calculated_gb': float,
                'profile_median_gb': Optional[float],
                'error_pct': Optional[float],
                'confidence': str,  # 'high', 'medium', 'low', 'none'
                'recommendation': str,
                'sample_count': int
            }
        """
        from ..utils.memory_profiler import ProfileDatabase

        calculated = self.runtime_overhead_gb

        try:
            db = ProfileDatabase()
            profiles = db.query_profiles(model_name, dpi, crop_mode, tolerance_dpi=50)

            if not profiles:
                return {
                    'calculated_gb': calculated,
                    'profile_median_gb': None,
                    'error_pct': None,
                    'confidence': 'none',
                    'recommendation': 'No historical data available. Run profiling to gather baseline.',
                    'sample_count': 0
                }

            # Calculate median from profiles
            import statistics
            peaks = [p.peak_memory_gb for p in profiles]
            median = statistics.median(peaks)

            # Calculate error
            error_pct = ((median - calculated) / calculated * 100) if calculated > 0 else 0

            # Determine confidence
            if len(profiles) >= 10:
                confidence = 'high'
            elif len(profiles) >= 5:
                confidence = 'medium'
            elif len(profiles) >= 3:
                confidence = 'low'
            else:
                confidence = 'none'

            # Generate recommendation
            if abs(error_pct) < 5.0:
                recommendation = f'✅ Calculations accurate (±{abs(error_pct):.1f}%)'
            elif error_pct < -5.0:
                recommendation = f'⚠️ UNDERESTIMATION detected ({error_pct:.1f}%). Increase overhead multipliers!'
            else:
                recommendation = f'ℹ️ Overestimation ({error_pct:+.1f}%). Consider reducing multipliers.'

            return {
                'calculated_gb': calculated,
                'profile_median_gb': median,
                'error_pct': error_pct,
                'confidence': confidence,
                'recommendation': recommendation,
                'sample_count': len(profiles)
            }

        except Exception as e:
            return {
                'calculated_gb': calculated,
                'profile_median_gb': None,
                'error_pct': None,
                'confidence': 'error',
                'recommendation': f'Error validating profiles: {str(e)}',
                'sample_count': 0
            }
    
    def _detect_gpus(self) -> List[GPUInfo]:
        """Detect all available GPUs and their specs."""
        if not torch.cuda.is_available():
            return []
        
        gpus = []
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            allocated = torch.cuda.memory_allocated(i) / (1024**3)
            total = props.total_memory / (1024**3)
            
            gpus.append(GPUInfo(
                device_id=i,
                name=props.name,
                total_memory_gb=total,
                allocated_memory_gb=allocated,
                free_memory_gb=total - allocated,
                compute_capability=(props.major, props.minor)
            ))
        return gpus

    def _is_wsl(self) -> bool:
        """
        Detect if running on Windows Subsystem for Linux.

        Returns:
            True if running on WSL, False otherwise
        """
        try:
            with open('/proc/version', 'r') as f:
                version_info = f.read().lower()
                return 'microsoft' in version_info or 'wsl' in version_info
        except (FileNotFoundError, IOError):
            return False

    def _detect_system_ram(self) -> SystemRAMInfo:
        """
        Detect system RAM specifications.

        Returns:
            SystemRAMInfo with memory statistics in GB
        """
        mem = psutil.virtual_memory()

        return SystemRAMInfo(
            total_gb=round(mem.total / (1024**3), 2),
            available_gb=round(mem.available / (1024**3), 2),
            used_gb=round(mem.used / (1024**3), 2),
            percent_used=round(mem.percent, 1),
            is_wsl=self._is_wsl()
        )

    def get_system_ram_info(self) -> SystemRAMInfo:
        """
        Get system RAM information.

        Returns:
            SystemRAMInfo with current memory statistics
        """
        # Refresh to get current stats
        return self._detect_system_ram()

    def _calculate_runtime_overhead(self) -> float:
        """
        Calculate runtime memory overhead for image processing.
        
        REVISED CALCULATIONS based on actual measurements:
        
        Previous (incorrect) assumptions:
        - Crop overhead: 2x multiplier
        - Activation overhead: 2.5x multiplier
        - Missing: KV cache, fragmentation buffer
        - Result: 1.27 GB at 300 DPI (6x underestimate)
        
        New (correct) calculations:
        - Crop overhead: 8x multiplier (DeepSeek creates 6-10 crops)
        - Activation overhead: 3x multiplier (includes attention maps)
        - KV cache: 2.5 GB (for max_new_tokens=4096)
        - Fragmentation: 1 GB (PyTorch memory management)
        - Result: ~7.5 GB at 300 DPI (matches actual usage)
        
        Memory components:
        1. Base image tensor (float32, 3 channels)
        2. Multiple resolution crops (DeepSeek's crop_mode)
        3. Attention maps (scale quadratically with sequence length)
        4. Activation tensors during forward pass
        5. KV cache for text generation
        6. PyTorch memory fragmentation overhead
        
        Args:
            None (uses self.dpi)
        
        Returns:
            Estimated peak overhead in GB during inference
        """
        # Legal size paper dimensions (worst case)
        width_inches, height_inches = 8.5, 14.0
        
        # Calculate pixel dimensions at given DPI
        width_px = int(width_inches * self.dpi)
        height_px = int(height_inches * self.dpi)
        
        # --- Component 1: Base Image Memory ---
        # Image tensor: width × height × 3 channels × 4 bytes (float32)
        image_bytes = width_px * height_px * 3 * 4
        image_gb = image_bytes / (1024**3)
        
        # --- Component 2: Crop Overhead ---
        # DeepSeek-OCR with crop_mode=True creates 6-10 crops at multiple resolutions
        # Each crop is processed separately
        # All crop tensors must exist in memory simultaneously
        # Measured multiplier: 8x (not 2x as previously assumed)
        crop_overhead_gb = image_gb * 8.0
        
        # --- Component 3: Attention and Activation Memory ---
        # During forward pass, model needs memory for:
        # - Attention maps (scale ~quadratically with sequence length)
        # - Intermediate activations in each layer
        # - Gradient buffers (even in inference due to implementation)
        # Updated multiplier: 4.5x to account for batched patch processing
        # With 6 patches + base (batch_size=7), attention memory is higher than single-image
        attention_overhead_gb = (image_gb + crop_overhead_gb) * 4.5
        
        # --- Component 4: KV Cache for Generation ---
        # Text generation with max_new_tokens=4096 (from config)
        # KV cache size: batch_size × num_layers × 2 × num_heads × seq_len × head_dim × 4 bytes
        # For DeepSeek-OCR generating 4096 tokens: ~2.5 GB
        # This is relatively constant regardless of image size
        generation_cache_gb = 2.5
        
        # --- Component 5: Memory Fragmentation Buffer ---
        # PyTorch's caching allocator can cause fragmentation
        # After loading/unloading models, available memory may be fragmented
        # Reserve 1GB buffer to prevent OOM from fragmentation
        fragmentation_buffer_gb = 1.0
        
        # --- Total Peak Memory ---
        # Sum of all components represents peak memory during inference
        total_overhead = (
            image_gb +                    # Base image
            crop_overhead_gb +            # Multiple crops
            attention_overhead_gb +       # Attention & activations
            generation_cache_gb +         # KV cache
            fragmentation_buffer_gb       # Fragmentation safety
        )
        
        return total_overhead
    
    def get_detailed_memory_breakdown(self) -> Dict[str, float]:
        """
        Get detailed breakdown of memory calculation for debugging.
        
        Returns:
            Dictionary with component-wise memory breakdown
        """
        width_px = int(8.5 * self.dpi)
        height_px = int(14.0 * self.dpi)
        
        image_gb = (width_px * height_px * 3 * 4) / (1024**3)
        crop_overhead_gb = image_gb * 8.0
        attention_overhead_gb = (image_gb + crop_overhead_gb) * 3.0
        generation_cache_gb = 2.5
        fragmentation_buffer_gb = 1.0
        
        return {
            'dpi': self.dpi,
            'resolution': f"{width_px}x{height_px}",
            'base_image_gb': round(image_gb, 3),
            'crop_overhead_gb': round(crop_overhead_gb, 3),
            'attention_activations_gb': round(attention_overhead_gb, 3),
            'generation_cache_gb': generation_cache_gb,
            'fragmentation_buffer_gb': fragmentation_buffer_gb,
            'total_overhead_gb': round(self.runtime_overhead_gb, 3)
        }
    
    def get_available_vram(self, device_id: int) -> float:
        """Get available VRAM on specific GPU (with safety buffer)."""
        if device_id >= len(self.gpus):
            return 0.0
        gpu = self.gpus[device_id]
        return max(0, gpu.free_memory_gb - self.SAFETY_BUFFER_GB)
    
    def can_fit_all_on_single_gpu(
        self, 
        models: List[ModelMemoryRequirement]
    ) -> Optional[int]:
        """
        Check if all models can fit on a single GPU.
        
        For persistent strategy where all models stay loaded:
        - Model weights are always in memory (sum all base_vram)
        - Runtime overhead is sequential (only max matters, not sum)
        - Peak memory = sum(base_vram) + max(runtime_overhead)
        
        Returns:
            GPU device_id if they fit, None otherwise
        """
        # Sum all model weights (always loaded)
        total_model_weights = sum(m.base_vram_gb for m in models)
        
        # Account for quantization on weights
        for m in models:
            if m.quantization == "int8":
                total_model_weights = total_model_weights * 0.5
            elif m.quantization == "int4":
                total_model_weights = total_model_weights * 0.25
        
        # Max runtime overhead (only one model infers at a time)
        max_runtime_overhead = max(m.runtime_overhead_gb for m in models) if models else 0
        
        # Peak memory during inference
        peak_required = total_model_weights + max_runtime_overhead
        
        # Try GPUs in order of available memory (largest first)
        # Compare against total GPU memory (not current free), since peak includes model weights
        for gpu in sorted(self.gpus, key=lambda g: g.free_memory_gb, reverse=True):
            # Total available = total memory - safety buffer
            total_available = gpu.total_memory_gb - self.SAFETY_BUFFER_GB
            if peak_required <= total_available:
                return gpu.device_id
        
        return None
    
    def can_fit_models_on_separate_gpus(
        self, 
        models: List[ModelMemoryRequirement]
    ) -> Optional[Dict[str, int]]:
        """
        Check if models can fit on separate GPUs.
        
        Returns:
            Dict mapping model_name -> gpu_id, or None if can't fit
        """
        if len(models) > len(self.gpus):
            return None
        
        # Sort models by VRAM requirement (largest first)
        sorted_models = sorted(models, key=lambda m: m.estimated_vram_gb(), reverse=True)
        
        # Sort GPUs by available VRAM (largest first)
        sorted_gpus = sorted(self.gpus, key=lambda g: g.free_memory_gb, reverse=True)
        
        assignment = {}
        for model in sorted_models:
            required = model.estimated_vram_gb()
            for gpu in sorted_gpus:
                if gpu.device_id not in assignment.values():
                    available = self.get_available_vram(gpu.device_id)
                    if required <= available:
                        assignment[model.model_name] = gpu.device_id
                        break
            
            if model.model_name not in assignment:
                return None  # Can't fit this model
        
        return assignment
    
    def can_shard_across_gpus(
        self, 
        model: ModelMemoryRequirement
    ) -> Optional[List[int]]:
        """
        Check if a large model can be sharded across multiple GPUs.
        
        Returns:
            List of GPU IDs to shard across, or None if not possible
        """
        total_available = sum(self.get_available_vram(g.device_id) for g in self.gpus)
        required = model.estimated_vram_gb()
        
        if required <= total_available:
            # Return all GPUs for sharding
            return [g.device_id for g in self.gpus]
        
        return None


@dataclass
class MemoryProfile:
    """Memory usage profile from actual inference run."""
    dpi: int
    page_size: str  # "letter", "legal", "a4"
    peak_memory_gb: float
    model_name: str
    crop_mode: bool
    timestamp: float


class MemoryProfiler:
    """
    Profile actual memory usage during inference and adjust calculations dynamically.
    
    This class records peak memory usage during PDF processing and caches
    the results to improve future memory estimations. After several runs,
    the system learns the actual memory requirements and adjusts calculations.
    """
    
    def __init__(self, cache_file: str = ".memory_profiles.json"):
        """
        Initialize memory profiler.
        
        Args:
            cache_file: Path to JSON file for caching profiles
        """
        self.cache_file = cache_file
        self.profiles: List[MemoryProfile] = []
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load cached memory profiles from disk."""
        import json
        from pathlib import Path
        
        cache_path = Path(self.cache_file)
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                    self.profiles = [MemoryProfile(**p) for p in data]
            except Exception as e:
                # If cache is corrupted, start fresh
                print(f"Warning: Could not load memory profiles: {e}")
                self.profiles = []
    
    def _save_cache(self) -> None:
        """Save memory profiles to disk."""
        import json
        from pathlib import Path
        
        try:
            data = [vars(p) for p in self.profiles]
            cache_path = Path(self.cache_file)
            
            # Ensure parent directory exists
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save memory profiles: {e}")
    
    def start_profiling(self, device_id: int) -> float:
        """
        Start memory profiling for an inference run.
        
        Call this BEFORE running inference.
        
        Args:
            device_id: GPU device ID to monitor
            
        Returns:
            Starting memory in GB (for delta calculation)
        """
        if not torch.cuda.is_available():
            return 0.0
        
        # Reset peak memory stats
        torch.cuda.reset_peak_memory_stats(device_id)
        
        # Record starting memory
        start_mem_bytes = torch.cuda.memory_allocated(device_id)
        start_mem_gb = start_mem_bytes / (1024**3)
        
        return start_mem_gb
    
    def end_profiling(self, device_id: int, start_mem_gb: float) -> float:
        """
        End memory profiling and get peak memory used.
        
        Call this AFTER inference completes.
        
        Args:
            device_id: GPU device ID that was monitored
            start_mem_gb: Starting memory from start_profiling()
            
        Returns:
            Peak memory delta in GB (amount used by inference)
        """
        if not torch.cuda.is_available():
            return 0.0
        
        # Get peak memory during inference
        peak_mem_bytes = torch.cuda.max_memory_allocated(device_id)
        peak_mem_gb = peak_mem_bytes / (1024**3)
        
        # Return delta (memory used by inference)
        return peak_mem_gb - start_mem_gb
    
    def add_profile(
        self,
        dpi: int,
        page_size: str,
        peak_memory_gb: float,
        model_name: str,
        crop_mode: bool
    ) -> None:
        """
        Add a new memory profile from an inference run.
        
        Args:
            dpi: DPI setting used
            page_size: Page size ("letter", "legal", "a4")
            peak_memory_gb: Peak memory used (GB)
            model_name: Model that was used
            crop_mode: Whether crop mode was enabled
        """
        import time
        
        profile = MemoryProfile(
            dpi=dpi,
            page_size=page_size,
            peak_memory_gb=peak_memory_gb,
            model_name=model_name,
            crop_mode=crop_mode,
            timestamp=time.time()
        )
        
        self.profiles.append(profile)
        self._save_cache()
    
    def get_adjustment_factor(
        self,
        dpi: int,
        model_name: str,
        crop_mode: bool
    ) -> Optional[float]:
        """
        Get memory adjustment factor based on historical profiles.
        
        Returns median peak memory from recent matching profiles,
        or None if insufficient data.
        
        Args:
            dpi: DPI setting
            model_name: Model name
            crop_mode: Whether crop mode enabled
            
        Returns:
            Median peak memory (GB) from profiles, or None if < 3 profiles
        """
        # Find matching profiles
        matching = [
            p for p in self.profiles
            if (p.dpi == dpi and 
                p.model_name == model_name and 
                p.crop_mode == crop_mode)
        ]
        
        # Need at least 3 data points for reliable adjustment
        if len(matching) < 3:
            return None
        
        # Use median of most recent 10 profiles
        recent = sorted(matching, key=lambda p: p.timestamp, reverse=True)[:10]
        peaks = [p.peak_memory_gb for p in recent]
        
        # Calculate median
        peaks.sort()
        median_idx = len(peaks) // 2
        median_peak = peaks[median_idx]
        
        return median_peak
    
    def get_profile_stats(self) -> Dict[str, any]:
        """
        Get statistics about collected profiles.
        
        Returns:
            Dictionary with profile statistics
        """
        if not self.profiles:
            return {
                'total_profiles': 0,
                'models': [],
                'dpi_settings': []
            }
        
        models = list(set(p.model_name for p in self.profiles))
        dpis = list(set(p.dpi for p in self.profiles))
        
        return {
            'total_profiles': len(self.profiles),
            'models': models,
            'dpi_settings': sorted(dpis),
            'oldest_profile': min(p.timestamp for p in self.profiles),
            'newest_profile': max(p.timestamp for p in self.profiles)
        }

