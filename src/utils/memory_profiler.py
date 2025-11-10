"""GPU memory profiling utilities for empirical VRAM measurement."""

import time
import torch
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from PIL import Image
import statistics

from ..models.gpu_memory_analyzer import GPUMemoryAnalyzer, ModelMemoryRequirement

logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """Single point-in-time GPU memory measurement."""
    timestamp: float  # Unix timestamp
    device_id: int
    allocated_gb: float  # torch.cuda.memory_allocated()
    reserved_gb: float   # torch.cuda.memory_reserved()
    peak_gb: float       # torch.cuda.max_memory_allocated()
    total_gb: float      # torch.cuda.get_device_properties().total_memory
    free_gb: float       # total_gb - allocated_gb

    @property
    def utilization(self) -> float:
        """Memory utilization as percentage (0.0-1.0)."""
        return self.allocated_gb / self.total_gb if self.total_gb > 0 else 0.0


@dataclass
class MemoryMeasurement:
    """Memory measurement for a specific configuration."""

    # Configuration
    model_name: str
    dpi: int
    crop_mode_enabled: bool
    strategy_name: str
    device_ids: List[int]

    # Calculated forecast (from GPUMemoryAnalyzer)
    calculated_base_gb: float
    calculated_overhead_gb: float
    calculated_peak_gb: float

    # Actual measurements
    baseline_snapshot: MemorySnapshot
    post_load_snapshot: MemorySnapshot
    post_inference_snapshot: MemorySnapshot

    # Derived metrics
    actual_load_gb: float = field(init=False)
    actual_inference_peak_gb: float = field(init=False)
    forecast_error_pct: float = field(init=False)

    # Status
    success: bool = True
    error_message: Optional[str] = None

    def __post_init__(self):
        """Calculate derived metrics."""
        self.actual_load_gb = (
            self.post_load_snapshot.allocated_gb -
            self.baseline_snapshot.allocated_gb
        )
        self.actual_inference_peak_gb = self.post_inference_snapshot.peak_gb

        # Calculate forecast error
        if self.calculated_peak_gb > 0:
            self.forecast_error_pct = (
                (self.actual_inference_peak_gb - self.calculated_peak_gb) /
                self.calculated_peak_gb * 100
            )
        else:
            self.forecast_error_pct = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "model_name": self.model_name,
            "dpi": self.dpi,
            "crop_mode_enabled": self.crop_mode_enabled,
            "strategy_name": self.strategy_name,
            "device_ids": self.device_ids,
            "calculated": {
                "base_gb": round(self.calculated_base_gb, 2),
                "overhead_gb": round(self.calculated_overhead_gb, 2),
                "peak_gb": round(self.calculated_peak_gb, 2)
            },
            "actual": {
                "load_gb": round(self.actual_load_gb, 2),
                "inference_peak_gb": round(self.actual_inference_peak_gb, 2),
                "post_load_allocated_gb": round(self.post_load_snapshot.allocated_gb, 2),
                "post_load_reserved_gb": round(self.post_load_snapshot.reserved_gb, 2)
            },
            "analysis": {
                "forecast_error_pct": round(self.forecast_error_pct, 1),
                "underestimated": self.forecast_error_pct < -5.0,
                "overestimated": self.forecast_error_pct > 5.0
            },
            "success": self.success,
            "error_message": self.error_message
        }


@dataclass
class ProfileReport:
    """Complete profiling report with analysis."""

    measurements: List[MemoryMeasurement]
    timestamp: str
    system_info: Dict[str, Any]

    # Aggregated statistics
    avg_error_pct: float = field(init=False)
    max_error_pct: float = field(init=False)
    min_error_pct: float = field(init=False)
    underestimated_count: int = field(init=False)
    overestimated_count: int = field(init=False)

    def __post_init__(self):
        """Calculate aggregated statistics."""
        successful = [m for m in self.measurements if m.success]

        if successful:
            errors = [m.forecast_error_pct for m in successful]
            self.avg_error_pct = statistics.mean(errors)
            self.max_error_pct = max(errors)
            self.min_error_pct = min(errors)
            self.underestimated_count = sum(1 for e in errors if e < -5.0)
            self.overestimated_count = sum(1 for e in errors if e > 5.0)
        else:
            self.avg_error_pct = 0.0
            self.max_error_pct = 0.0
            self.min_error_pct = 0.0
            self.underestimated_count = 0
            self.overestimated_count = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "metadata": {
                "timestamp": self.timestamp,
                "total_tests": len(self.measurements),
                "successful_tests": sum(1 for m in self.measurements if m.success),
                "failed_tests": sum(1 for m in self.measurements if not m.success)
            },
            "system_info": self.system_info,
            "summary": {
                "avg_error_pct": round(self.avg_error_pct, 1),
                "max_error_pct": round(self.max_error_pct, 1),
                "min_error_pct": round(self.min_error_pct, 1),
                "underestimated_count": self.underestimated_count,
                "overestimated_count": self.overestimated_count
            },
            "measurements": [m.to_dict() for m in self.measurements]
        }


class MemoryProfiler:
    """GPU memory profiler for model loading and inference."""

    def __init__(self, verbose: bool = True):
        """
        Initialize memory profiler.

        Args:
            verbose: Print detailed progress messages
        """
        self.verbose = verbose
        self.measurements: List[MemoryMeasurement] = []

    def capture_snapshot(self, device_id: int = 0) -> MemorySnapshot:
        """
        Capture current GPU memory state.

        Args:
            device_id: CUDA device ID

        Returns:
            MemorySnapshot with current memory stats
        """
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available")

        device = torch.device(f"cuda:{device_id}")
        props = torch.cuda.get_device_properties(device)

        allocated = torch.cuda.memory_allocated(device) / (1024**3)
        reserved = torch.cuda.memory_reserved(device) / (1024**3)
        peak = torch.cuda.max_memory_allocated(device) / (1024**3)
        total = props.total_memory / (1024**3)

        return MemorySnapshot(
            timestamp=time.time(),
            device_id=device_id,
            allocated_gb=allocated,
            reserved_gb=reserved,
            peak_gb=peak,
            total_gb=total,
            free_gb=total - allocated
        )

    def reset_peak_stats(self, device_id: int = 0):
        """Reset peak memory statistics for a device."""
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats(device_id)

    def measure_model_loading(
        self,
        model_manager,
        model_name: str,
        dpi: int,
        disable_crop_mode: bool,
        strategy_name: str,
        device_ids: List[int],
        sample_image: Image.Image
    ) -> MemoryMeasurement:
        """
        Measure memory usage for model loading and inference.

        Args:
            model_manager: ModelManager instance
            model_name: Name of model to load
            dpi: DPI setting for runtime overhead calculation
            disable_crop_mode: Whether crop mode is disabled
            strategy_name: Loading strategy name
            device_ids: List of GPU device IDs being used
            sample_image: Sample image for inference test

        Returns:
            MemoryMeasurement with complete profiling data
        """
        primary_device = device_ids[0]

        # Step 1: Get calculated forecast
        analyzer = GPUMemoryAnalyzer(dpi=dpi, enable_profiling=False)
        config = model_manager.model_configs[model_name]
        vram_str = config.get("vram_requirement", "6GB")
        base_vram_gb = float(vram_str.replace("GB", "").split("-")[0])

        # Calculate runtime overhead
        runtime_overhead = analyzer.runtime_overhead_gb
        if disable_crop_mode and model_name == "deepseek-ocr":
            runtime_overhead *= 0.47  # Adjustment for crop mode disabled

        calculated_peak = base_vram_gb + runtime_overhead

        # Step 2: Capture baseline
        torch.cuda.empty_cache()
        self.reset_peak_stats(primary_device)
        baseline_snapshot = self.capture_snapshot(primary_device)

        if self.verbose:
            print(f"\n[Profile] Testing: {model_name}")
            print(f"  DPI: {dpi}, Crop: {not disable_crop_mode}, Strategy: {strategy_name}")
            print(f"  Calculated peak: {calculated_peak:.2f}GB")
            print(f"  Baseline: {baseline_snapshot.allocated_gb:.2f}GB allocated")

        try:
            # Step 3: Load model
            model_instance = model_manager.load_model(
                model_name,
                force_disable_crop=disable_crop_mode
            )

            post_load_snapshot = self.capture_snapshot(primary_device)

            if self.verbose:
                print(f"  Post-load: {post_load_snapshot.allocated_gb:.2f}GB allocated")

            # Step 4: Run inference
            self.reset_peak_stats(primary_device)

            if model_name == "deepseek-ocr":
                _ = model_instance.extract_text(sample_image)
            else:  # Qwen models
                _ = model_instance.generate(
                    image=sample_image,
                    prompt="Describe this image briefly."
                )

            post_inference_snapshot = self.capture_snapshot(primary_device)

            if self.verbose:
                print(f"  Post-inference peak: {post_inference_snapshot.peak_gb:.2f}GB")
                print(f"  Forecast error: {((post_inference_snapshot.peak_gb - calculated_peak) / calculated_peak * 100):.1f}%")

            # Step 5: Create measurement
            measurement = MemoryMeasurement(
                model_name=model_name,
                dpi=dpi,
                crop_mode_enabled=not disable_crop_mode,
                strategy_name=strategy_name,
                device_ids=device_ids,
                calculated_base_gb=base_vram_gb,
                calculated_overhead_gb=runtime_overhead,
                calculated_peak_gb=calculated_peak,
                baseline_snapshot=baseline_snapshot,
                post_load_snapshot=post_load_snapshot,
                post_inference_snapshot=post_inference_snapshot,
                success=True,
                error_message=None
            )

        except Exception as e:
            if self.verbose:
                print(f"  ✗ Failed: {str(e)}")

            # Create failed measurement
            measurement = MemoryMeasurement(
                model_name=model_name,
                dpi=dpi,
                crop_mode_enabled=not disable_crop_mode,
                strategy_name=strategy_name,
                device_ids=device_ids,
                calculated_base_gb=base_vram_gb,
                calculated_overhead_gb=runtime_overhead,
                calculated_peak_gb=calculated_peak,
                baseline_snapshot=baseline_snapshot,
                post_load_snapshot=baseline_snapshot,  # Use baseline as fallback
                post_inference_snapshot=baseline_snapshot,  # Use baseline as fallback
                success=False,
                error_message=str(e)
            )

        finally:
            # Cleanup
            if model_manager.current_model_name:
                model_manager.unload_model(model_manager.current_model_name)
            torch.cuda.empty_cache()

        self.measurements.append(measurement)
        return measurement

    def generate_report(self, timestamp: str) -> ProfileReport:
        """
        Generate comprehensive report from measurements.

        Args:
            timestamp: ISO format timestamp for report

        Returns:
            ProfileReport with all measurements and analysis
        """
        # Gather system info
        system_info = {
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda if torch.cuda.is_available() else None,
            "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "gpus": []
        }

        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                system_info["gpus"].append({
                    "id": i,
                    "name": props.name,
                    "total_memory_gb": round(props.total_memory / (1024**3), 2),
                    "compute_capability": f"{props.major}.{props.minor}"
                })

        return ProfileReport(
            measurements=self.measurements,
            timestamp=timestamp,
            system_info=system_info
        )


# ============================================================================
# Enhanced Profiling Classes for Production Integration
# ============================================================================


@dataclass
class MemoryProfile:
    """Simplified profile record for persistence."""
    model_name: str
    dpi: int
    crop_mode: bool
    peak_memory_gb: float
    calculated_memory_gb: float
    timestamp: str
    page_size: Optional[str] = None  # e.g., "letter", "legal", "a4"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryProfile':
        """Create from dictionary."""
        return cls(**data)


class ProfileDatabase:
    """Manages persistent storage and retrieval of memory profiles."""

    def __init__(self, db_path: str = ".memory_profiles.json"):
        """
        Initialize profile database.

        Args:
            db_path: Path to JSON database file
        """
        self.db_path = Path(db_path)
        self.profiles: List[MemoryProfile] = []
        self._load_profiles()

    def _load_profiles(self):
        """Load profiles from disk."""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                    self.profiles = [MemoryProfile.from_dict(p) for p in data.get('profiles', [])]
                logger.info(f"Loaded {len(self.profiles)} memory profiles from {self.db_path}")
            except Exception as e:
                logger.warning(f"Failed to load profiles from {self.db_path}: {e}")
                self.profiles = []
        else:
            logger.info(f"No existing profile database at {self.db_path}")

    def save_profile(self, profile: MemoryProfile):
        """
        Add profile and persist to disk.

        Args:
            profile: MemoryProfile to save
        """
        self.profiles.append(profile)
        self._persist()
        logger.info(f"Saved profile: {profile.model_name} @ {profile.dpi}DPI, peak={profile.peak_memory_gb:.2f}GB")

    def _persist(self):
        """Write profiles to disk."""
        try:
            data = {
                'version': '1.0',
                'last_updated': datetime.now().isoformat(),
                'profiles': [p.to_dict() for p in self.profiles]
            }
            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist profiles to {self.db_path}: {e}")

    def query_profiles(
        self,
        model_name: str,
        dpi: int,
        crop_mode: bool,
        tolerance_dpi: int = 50
    ) -> List[MemoryProfile]:
        """
        Query profiles matching criteria.

        Args:
            model_name: Model name to match
            dpi: DPI setting to match
            crop_mode: Crop mode to match
            tolerance_dpi: DPI tolerance for matching (default ±50)

        Returns:
            List of matching profiles
        """
        matches = []
        for profile in self.profiles:
            if (profile.model_name == model_name and
                profile.crop_mode == crop_mode and
                abs(profile.dpi - dpi) <= tolerance_dpi):
                matches.append(profile)
        return matches

    def get_recommendation(
        self,
        model_name: str,
        dpi: int,
        crop_mode: bool,
        min_samples: int = 3
    ) -> Optional[float]:
        """
        Get recommended memory from historical profiles.

        Args:
            model_name: Model name
            dpi: DPI setting
            crop_mode: Crop mode enabled
            min_samples: Minimum profiles required for recommendation

        Returns:
            Median peak memory in GB, or None if insufficient data
        """
        matches = self.query_profiles(model_name, dpi, crop_mode)

        if len(matches) < min_samples:
            logger.debug(f"Insufficient profiles for {model_name} @ {dpi}DPI: {len(matches)} < {min_samples}")
            return None

        # Use median of most recent 10 profiles
        recent = sorted(matches, key=lambda p: p.timestamp, reverse=True)[:10]
        peaks = [p.peak_memory_gb for p in recent]
        median = statistics.median(peaks)

        logger.info(f"Recommendation for {model_name} @ {dpi}DPI: {median:.2f}GB (from {len(recent)} profiles)")
        return median

    def cleanup_old_profiles(self, retention_days: int = 90):
        """
        Remove profiles older than retention period.

        Args:
            retention_days: Days to retain profiles
        """
        cutoff = datetime.now() - timedelta(days=retention_days)
        cutoff_str = cutoff.isoformat()

        original_count = len(self.profiles)
        self.profiles = [p for p in self.profiles if p.timestamp >= cutoff_str]
        removed = original_count - len(self.profiles)

        if removed > 0:
            self._persist()
            logger.info(f"Cleaned up {removed} old profiles (>{retention_days} days)")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about profile database."""
        if not self.profiles:
            return {
                'total_profiles': 0,
                'models': [],
                'dpi_settings': [],
                'date_range': None
            }

        return {
            'total_profiles': len(self.profiles),
            'models': list(set(p.model_name for p in self.profiles)),
            'dpi_settings': sorted(set(p.dpi for p in self.profiles)),
            'date_range': {
                'oldest': min(p.timestamp for p in self.profiles),
                'newest': max(p.timestamp for p in self.profiles)
            }
        }


class InferenceProfiler:
    """Lightweight profiler for production inference tracking."""

    def __init__(self, db_path: str = ".memory_profiles.json"):
        """
        Initialize inference profiler.

        Args:
            db_path: Path to profile database
        """
        self.db = ProfileDatabase(db_path)
        self._active_profiles: Dict[int, Dict[str, Any]] = {}

    def start_inference(self, device_id: int = 0) -> Dict[str, Any]:
        """
        Capture pre-inference state.

        Args:
            device_id: CUDA device ID

        Returns:
            State dictionary for end_inference()
        """
        if not torch.cuda.is_available():
            logger.warning("CUDA not available, profiling disabled")
            return {'disabled': True}

        try:
            device = torch.device(f"cuda:{device_id}")

            # Clear cache and reset peak stats
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats(device_id)

            allocated = torch.cuda.memory_allocated(device) / (1024**3)

            state = {
                'device_id': device_id,
                'start_time': time.time(),
                'start_allocated_gb': allocated,
                'disabled': False
            }

            self._active_profiles[device_id] = state
            return state

        except Exception as e:
            logger.error(f"Failed to start inference profiling: {e}")
            return {'disabled': True}

    def end_inference(
        self,
        device_id: int,
        start_state: Dict[str, Any]
    ) -> Optional[MemorySnapshot]:
        """
        Capture post-inference peak.

        Args:
            device_id: CUDA device ID
            start_state: State from start_inference()

        Returns:
            MemorySnapshot with peak memory, or None if profiling disabled
        """
        if start_state.get('disabled'):
            return None

        try:
            device = torch.device(f"cuda:{device_id}")
            props = torch.cuda.get_device_properties(device)

            allocated = torch.cuda.memory_allocated(device) / (1024**3)
            reserved = torch.cuda.memory_reserved(device) / (1024**3)
            peak = torch.cuda.max_memory_allocated(device) / (1024**3)
            total = props.total_memory / (1024**3)

            snapshot = MemorySnapshot(
                timestamp=time.time(),
                device_id=device_id,
                allocated_gb=allocated,
                reserved_gb=reserved,
                peak_gb=peak,
                total_gb=total,
                free_gb=total - allocated
            )

            # Clean up active profile
            if device_id in self._active_profiles:
                del self._active_profiles[device_id]

            return snapshot

        except Exception as e:
            logger.error(f"Failed to end inference profiling: {e}")
            return None

    def record_inference(
        self,
        model_name: str,
        dpi: int,
        crop_mode: bool,
        snapshot: MemorySnapshot,
        calculated_memory_gb: float,
        page_size: Optional[str] = None
    ):
        """
        Save inference measurement to database.

        Args:
            model_name: Name of model used
            dpi: DPI setting
            crop_mode: Whether crop mode enabled
            snapshot: Memory snapshot from end_inference()
            calculated_memory_gb: Calculated memory requirement
            page_size: Optional page size (letter, legal, etc.)
        """
        if snapshot is None:
            return

        profile = MemoryProfile(
            model_name=model_name,
            dpi=dpi,
            crop_mode=crop_mode,
            peak_memory_gb=snapshot.peak_gb,
            calculated_memory_gb=calculated_memory_gb,
            timestamp=datetime.now().isoformat(),
            page_size=page_size
        )

        self.db.save_profile(profile)


class ProfileAnalyzer:
    """Analyzes profile database for insights and recommendations."""

    def __init__(self, db_path: str = ".memory_profiles.json"):
        """
        Initialize analyzer.

        Args:
            db_path: Path to profile database
        """
        self.db = ProfileDatabase(db_path)

    def calculate_error_stats(self) -> Dict[str, Any]:
        """
        Calculate forecast error statistics across all profiles.

        Returns:
            Dictionary with error statistics
        """
        if not self.db.profiles:
            return {
                'total': 0,
                'avg_error_pct': 0.0,
                'max_error_pct': 0.0,
                'min_error_pct': 0.0,
                'underestimated_count': 0,
                'overestimated_count': 0
            }

        errors = []
        for profile in self.db.profiles:
            if profile.calculated_memory_gb > 0:
                error_pct = (
                    (profile.peak_memory_gb - profile.calculated_memory_gb) /
                    profile.calculated_memory_gb * 100
                )
                errors.append(error_pct)

        if not errors:
            return {'total': 0, 'avg_error_pct': 0.0, 'max_error_pct': 0.0,
                    'min_error_pct': 0.0, 'underestimated_count': 0, 'overestimated_count': 0}

        return {
            'total': len(self.db.profiles),
            'avg_error_pct': statistics.mean(errors),
            'max_error_pct': max(errors),
            'min_error_pct': min(errors),
            'underestimated_count': sum(1 for e in errors if e < -5.0),
            'overestimated_count': sum(1 for e in errors if e > 5.0),
            'std_dev_pct': statistics.stdev(errors) if len(errors) > 1 else 0.0
        }

    def identify_underestimation(self, threshold: float = -5.0) -> List[Dict[str, Any]]:
        """
        Find profiles with significant underestimation.

        Args:
            threshold: Error percentage threshold (negative = underestimation)

        Returns:
            List of problematic profiles with details
        """
        problems = []

        for profile in self.db.profiles:
            if profile.calculated_memory_gb > 0:
                error_pct = (
                    (profile.peak_memory_gb - profile.calculated_memory_gb) /
                    profile.calculated_memory_gb * 100
                )

                if error_pct < threshold:
                    problems.append({
                        'model_name': profile.model_name,
                        'dpi': profile.dpi,
                        'crop_mode': profile.crop_mode,
                        'calculated_gb': profile.calculated_memory_gb,
                        'actual_gb': profile.peak_memory_gb,
                        'error_pct': error_pct,
                        'timestamp': profile.timestamp
                    })

        # Sort by error (worst first)
        problems.sort(key=lambda x: x['error_pct'])
        return problems

    def generate_tuning_recommendations(self) -> List[str]:
        """
        Generate actionable tuning recommendations.

        Returns:
            List of recommendation strings
        """
        recommendations = []
        stats = self.calculate_error_stats()

        if stats['total'] == 0:
            return ["No profiles available for analysis. Run profiling first."]

        # Check for systematic underestimation
        if stats['underestimated_count'] > 0:
            pct = (stats['underestimated_count'] / stats['total']) * 100
            recommendations.append(
                f"⚠️ {stats['underestimated_count']} profiles ({pct:.1f}%) show >5% underestimation"
            )

            # Identify worst offenders
            problems = self.identify_underestimation()
            if problems:
                worst = problems[0]
                recommendations.append(
                    f"  Worst case: {worst['model_name']} @ {worst['dpi']}DPI "
                    f"({worst['error_pct']:.1f}% error)"
                )

                # Model-specific recommendations
                model_issues = {}
                for p in problems:
                    model = p['model_name']
                    if model not in model_issues:
                        model_issues[model] = []
                    model_issues[model].append(p['error_pct'])

                for model, errors in model_issues.items():
                    avg_error = statistics.mean(errors)
                    recommendations.append(
                        f"  {model}: Increase overhead multiplier by ~{abs(avg_error)/10:.1f}x"
                    )

        # Check for overestimation
        if stats['overestimated_count'] > 0:
            pct = (stats['overestimated_count'] / stats['total']) * 100
            recommendations.append(
                f"ℹ️ {stats['overestimated_count']} profiles ({pct:.1f}%) show >5% overestimation"
            )
            recommendations.append(
                "  Consider reducing overhead multipliers for better GPU utilization"
            )

        # Check accuracy
        if abs(stats['avg_error_pct']) < 5.0:
            recommendations.append(
                f"✅ Average error {stats['avg_error_pct']:.1f}% - calculations are accurate"
            )

        # Check consistency
        if stats.get('std_dev_pct', 0) > 10.0:
            recommendations.append(
                f"⚠️ High variance (σ={stats['std_dev_pct']:.1f}%) - "
                "memory usage inconsistent across runs"
            )

        return recommendations if recommendations else ["No specific recommendations at this time."]

    def get_model_breakdown(self) -> Dict[str, Dict[str, Any]]:
        """
        Get per-model statistics.

        Returns:
            Dictionary mapping model_name to statistics
        """
        breakdown = {}

        for profile in self.db.profiles:
            model = profile.model_name
            if model not in breakdown:
                breakdown[model] = {
                    'count': 0,
                    'avg_peak_gb': 0.0,
                    'max_peak_gb': 0.0,
                    'min_peak_gb': float('inf'),
                    'peaks': []
                }

            breakdown[model]['count'] += 1
            breakdown[model]['peaks'].append(profile.peak_memory_gb)
            breakdown[model]['max_peak_gb'] = max(breakdown[model]['max_peak_gb'], profile.peak_memory_gb)
            breakdown[model]['min_peak_gb'] = min(breakdown[model]['min_peak_gb'], profile.peak_memory_gb)

        # Calculate averages
        for model, data in breakdown.items():
            if data['peaks']:
                data['avg_peak_gb'] = statistics.mean(data['peaks'])
                del data['peaks']  # Remove raw data

        return breakdown
