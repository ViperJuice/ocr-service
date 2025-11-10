"""GPU utility functions."""
import torch
from typing import Dict, List
import gc


def check_cuda_available() -> bool:
    """
    Check if CUDA is available.
    
    Returns:
        True if CUDA is available
    """
    return torch.cuda.is_available()


def get_gpu_info() -> Dict[str, any]:
    """
    Get GPU information.
    
    Returns:
        Dict with GPU details
    """
    if not torch.cuda.is_available():
        return {
            "cuda_available": False,
            "device_count": 0,
            "devices": [],
        }
    
    devices = []
    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        allocated = torch.cuda.memory_allocated(i) / 1024**3
        reserved = torch.cuda.memory_reserved(i) / 1024**3
        total = props.total_memory / 1024**3
        
        devices.append({
            "id": i,
            "name": torch.cuda.get_device_name(i),
            "compute_capability": f"{props.major}.{props.minor}",
            "total_memory_gb": round(total, 2),
            "allocated_gb": round(allocated, 2),
            "reserved_gb": round(reserved, 2),
            "free_gb": round(total - allocated, 2),
            "utilization_percent": round((allocated / total) * 100, 1),
        })
    
    total_memory = sum(d["total_memory_gb"] for d in devices)
    total_allocated = sum(d["allocated_gb"] for d in devices)
    
    return {
        "cuda_available": True,
        "cuda_version": torch.version.cuda,
        "device_count": torch.cuda.device_count(),
        "devices": devices,
        "total_memory_gb": round(total_memory, 2),
        "total_allocated_gb": round(total_allocated, 2),
        "total_free_gb": round(total_memory - total_allocated, 2),
        "overall_utilization_percent": round((total_allocated / total_memory) * 100, 1),
    }


def clear_gpu_memory() -> None:
    """Clear GPU memory cache and run garbage collection."""
    gc.collect()
    
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def get_memory_summary() -> str:
    """
    Get formatted memory summary.
    
    Returns:
        Formatted string with memory info
    """
    info = get_gpu_info()
    
    if not info["cuda_available"]:
        return "CUDA not available"
    
    lines = [
        f"GPU Memory Summary:",
        f"  Devices: {info['device_count']}",
        f"  Total Memory: {info['total_memory_gb']:.2f} GB",
        f"  Allocated: {info['total_allocated_gb']:.2f} GB ({info['overall_utilization_percent']}%)",
        f"  Free: {info['total_free_gb']:.2f} GB",
        "",
    ]
    
    for device in info["devices"]:
        lines.extend([
            f"  GPU {device['id']}: {device['name']}",
            f"    Memory: {device['allocated_gb']:.2f} / {device['total_memory_gb']:.2f} GB ({device['utilization_percent']}%)",
        ])
    
    return "\n".join(lines)

