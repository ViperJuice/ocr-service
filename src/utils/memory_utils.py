"""GPU memory management utilities for optimizing VRAM usage."""
import gc
import torch
from typing import Dict
from contextlib import contextmanager
from PIL import Image


def clear_gpu_cache() -> None:
    """
    Clear CUDA cache and run garbage collection.
    
    This helps free up fragmented GPU memory between inference passes.
    """
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    gc.collect()


def get_gpu_memory_info() -> Dict[str, Dict[str, float]]:
    """
    Get detailed GPU memory usage for all devices.
    
    Returns:
        Dict mapping device names to memory info (allocated, free, total in GB)
    """
    if not torch.cuda.is_available():
        return {}
    
    memory_info = {}
    for i in range(torch.cuda.device_count()):
        allocated = torch.cuda.memory_allocated(i) / 1024**3
        reserved = torch.cuda.memory_reserved(i) / 1024**3
        total = torch.cuda.get_device_properties(i).total_memory / 1024**3
        free = total - allocated
        
        memory_info[f"cuda:{i}"] = {
            "allocated_gb": round(allocated, 2),
            "reserved_gb": round(reserved, 2),
            "free_gb": round(free, 2),
            "total_gb": round(total, 2),
            "utilization_percent": round((allocated / total) * 100, 1)
        }
    
    return memory_info


def estimate_image_memory_usage(image: Image.Image) -> float:
    """
    Estimate GPU memory needed for image processing (in GB).
    
    This is a rough estimate based on image dimensions and typical
    model processing overhead.
    
    Args:
        image: PIL Image to estimate memory for
        
    Returns:
        Estimated memory usage in GB
    """
    # Calculate raw image size
    width, height = image.size
    channels = 3  # RGB
    bytes_per_pixel = 4  # float32
    
    # Raw image memory
    image_memory = (width * height * channels * bytes_per_pixel) / 1024**3
    
    # Estimate processing overhead (model activations, intermediate tensors)
    # Typical overhead is 10-20x the image size for vision models
    processing_overhead = 15
    
    total_estimate = image_memory * processing_overhead
    
    return round(total_estimate, 2)


def has_sufficient_memory(required_gb: float, device: int = 0, safety_margin_gb: float = 1.0) -> bool:
    """
    Check if GPU has enough free memory for an operation.
    
    Args:
        required_gb: Required memory in GB
        device: CUDA device index
        safety_margin_gb: Additional margin to keep free
        
    Returns:
        True if sufficient memory is available
    """
    if not torch.cuda.is_available():
        return False
    
    if device >= torch.cuda.device_count():
        return False
    
    allocated = torch.cuda.memory_allocated(device) / 1024**3
    total = torch.cuda.get_device_properties(device).total_memory / 1024**3
    free = total - allocated
    
    return free >= (required_gb + safety_margin_gb)


@contextmanager
def memory_efficient_inference():
    """
    Context manager that clears cache before and after inference.
    
    Usage:
        with memory_efficient_inference():
            result = model.process_image(image)
    """
    # Clear cache before
    clear_gpu_cache()
    
    try:
        yield
    finally:
        # Clear cache after
        clear_gpu_cache()


def get_memory_summary() -> str:
    """
    Get a formatted string summary of GPU memory usage.
    
    Returns:
        Human-readable memory summary
    """
    if not torch.cuda.is_available():
        return "CUDA not available"
    
    info = get_gpu_memory_info()
    lines = []
    
    for device, stats in info.items():
        lines.append(
            f"{device}: {stats['allocated_gb']:.2f}GB / {stats['total_gb']:.2f}GB "
            f"({stats['utilization_percent']}% used, {stats['free_gb']:.2f}GB free)"
        )
    
    return "\n".join(lines)




