"""System capability detection for quality tier selection."""
import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class CapabilityDetector:
    """
    Detects system capabilities and determines maximum quality tier.

    Quality tiers are defined in the resource management spec:
    - Tier 1 (100%): Full precision, maximum quality
    - Tier 2 (85%): Reduced quality (NOT used for concurrency)
    - Tier 3 (80%): Further reduced quality
    - Tier 4 (70%): Minimal acceptable quality
    - Tier 5 (60%): Emergency fallback

    This system prioritizes QUALITY OVER SPEED. Lower tiers exist ONLY
    for systems that cannot physically run Tier 1.
    """

    # VRAM requirements per tier (in GB) for DeepSeek-OCR on 2-GPU setup
    # Based on actual memory profiling and HuggingFace's device_map allocation
    TIER_VRAM_REQUIREMENTS = {
        1: {"description": "Full precision (fp16/bf16)", "vram_per_gpu": 14.0},
        2: {"description": "Mixed precision", "vram_per_gpu": 12.0},
        3: {"description": "8-bit quantization", "vram_per_gpu": 8.0},
        4: {"description": "4-bit quantization", "vram_per_gpu": 5.0},
        5: {"description": "Aggressive 4-bit + offloading", "vram_per_gpu": 3.0},
    }

    @staticmethod
    def detect_max_tier(gpu_capacities: Dict[int, float]) -> Tuple[int, Dict]:
        """
        Detect the maximum quality tier the system can support.

        Args:
            gpu_capacities: Dict mapping GPU ID to usable VRAM in GB
                Example: {0: 22.0, 1: 22.0}

        Returns:
            Tuple of (max_tier, tier_info) where:
                - max_tier: Integer 1-5 representing maximum tier
                - tier_info: Dict with tier details

        Example:
            >>> detect_max_tier({0: 22.0, 1: 22.0})
            (1, {"tier": 1, "description": "Full precision", "vram_per_gpu": 14.0})
        """
        if not gpu_capacities:
            logger.warning("No GPUs available - defaulting to Tier 5 (CPU fallback)")
            return 5, CapabilityDetector.TIER_VRAM_REQUIREMENTS[5]

        # Get minimum VRAM across all GPUs (bottleneck)
        min_vram = min(gpu_capacities.values())
        gpu_count = len(gpu_capacities)

        logger.info(
            f"Detecting capability: {gpu_count} GPU(s), "
            f"min VRAM: {min_vram:.1f}GB per GPU"
        )

        # Check tiers in descending order (highest quality first)
        for tier in sorted(CapabilityDetector.TIER_VRAM_REQUIREMENTS.keys()):
            tier_info = CapabilityDetector.TIER_VRAM_REQUIREMENTS[tier]
            required_vram = tier_info["vram_per_gpu"]

            if min_vram >= required_vram:
                logger.info(
                    f"System supports Tier {tier}: {tier_info['description']} "
                    f"(requires {required_vram:.1f}GB, available {min_vram:.1f}GB)"
                )
                return tier, {
                    "tier": tier,
                    "description": tier_info["description"],
                    "vram_per_gpu": required_vram,
                    "vram_requirements": {gpu_id: required_vram for gpu_id in gpu_capacities.keys()}
                }

        # Fallback to Tier 5 if nothing else fits
        logger.warning(
            f"Insufficient VRAM for any tier (min: {min_vram:.1f}GB). "
            f"Falling back to Tier 5."
        )
        tier_info = CapabilityDetector.TIER_VRAM_REQUIREMENTS[5]
        return 5, {
            "tier": 5,
            "description": tier_info["description"],
            "vram_per_gpu": tier_info["vram_per_gpu"],
            "vram_requirements": {gpu_id: tier_info["vram_per_gpu"] for gpu_id in gpu_capacities.keys()}
        }

    @staticmethod
    def get_tier_config(tier: int, model_name: str = "deepseek-ocr") -> Dict:
        """
        Get model configuration for a specific quality tier.

        Args:
            tier: Quality tier (1-5)
            model_name: Model identifier

        Returns:
            Dict with HuggingFace model loading parameters

        Note:
            These configs will be used by ModelManager to configure
            the model via HuggingFace's from_pretrained() arguments.
        """
        if tier not in CapabilityDetector.TIER_VRAM_REQUIREMENTS:
            raise ValueError(f"Invalid tier: {tier}. Must be 1-5.")

        # Tier 1: Full precision, maximum quality
        if tier == 1:
            return {
                "torch_dtype": "auto",  # Use model's native dtype (fp16/bf16)
                "device_map": "auto",
                "load_in_8bit": False,
                "load_in_4bit": False,
            }

        # Tier 2: Mixed precision (still very high quality)
        elif tier == 2:
            return {
                "torch_dtype": "float16",
                "device_map": "auto",
                "load_in_8bit": False,
                "load_in_4bit": False,
            }

        # Tier 3: 8-bit quantization
        elif tier == 3:
            return {
                "torch_dtype": "auto",
                "device_map": "auto",
                "load_in_8bit": True,
                "load_in_4bit": False,
            }

        # Tier 4: 4-bit quantization
        elif tier == 4:
            return {
                "torch_dtype": "auto",
                "device_map": "auto",
                "load_in_8bit": False,
                "load_in_4bit": True,
                "bnb_4bit_compute_dtype": "float16",
            }

        # Tier 5: Aggressive 4-bit + CPU offloading
        elif tier == 5:
            return {
                "torch_dtype": "auto",
                "device_map": "auto",
                "load_in_8bit": False,
                "load_in_4bit": True,
                "bnb_4bit_compute_dtype": "float16",
                "offload_buffers": True,
            }
