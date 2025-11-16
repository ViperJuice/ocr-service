"""
Lightweight GPU Utility Functions

Replaces PyTorch-based GPU management with pynvml (NVIDIA Management Library).
This module is ONLY for monitoring and memory management - NOT for model inference.
Model inference happens in Docker containers.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import pynvml (NVIDIA Management Library)
try:
    import pynvml
    PYNVML_AVAILABLE = True
    _nvml_initialized = False
except ImportError:
    PYNVML_AVAILABLE = False
    _nvml_initialized = False
    logger.warning("pynvml not available - GPU monitoring disabled")


def initialize_nvml() -> bool:
    """
    Initialize NVIDIA Management Library

    Returns:
        bool: True if initialization successful, False otherwise
    """
    global _nvml_initialized

    if not PYNVML_AVAILABLE:
        return False

    if _nvml_initialized:
        return True

    try:
        pynvml.nvmlInit()
        _nvml_initialized = True
        logger.info("NVML initialized successfully")
        return True
    except Exception as e:
        logger.warning(f"Failed to initialize NVML: {e}")
        return False


def shutdown_nvml():
    """Shutdown NVIDIA Management Library"""
    global _nvml_initialized

    if _nvml_initialized and PYNVML_AVAILABLE:
        try:
            pynvml.nvmlShutdown()
            _nvml_initialized = False
        except Exception as e:
            logger.warning(f"Failed to shutdown NVML: {e}")


def is_gpu_available() -> bool:
    """
    Check if CUDA-capable GPUs are available

    Returns:
        bool: True if GPUs are available and NVML is initialized
    """
    if not PYNVML_AVAILABLE:
        return False

    if not _nvml_initialized and not initialize_nvml():
        return False

    try:
        device_count = pynvml.nvmlDeviceGetCount()
        return device_count > 0
    except Exception:
        return False


def get_gpu_count() -> int:
    """
    Get number of available GPUs

    Returns:
        int: Number of GPUs, or 0 if unavailable
    """
    if not is_gpu_available():
        return 0

    try:
        return pynvml.nvmlDeviceGetCount()
    except Exception as e:
        logger.warning(f"Failed to get GPU count: {e}")
        return 0


def empty_cache():
    """
    Clear GPU memory cache

    Note: With pynvml, we can't directly clear cache like torch.cuda.empty_cache().
    This is a no-op placeholder for compatibility with existing code.
    The actual memory management happens inside Docker containers.
    """
    # No-op: Memory management happens in containers
    pass


def synchronize(device_id: Optional[int] = None):
    """
    Synchronize GPU operations

    Note: This is a no-op placeholder for compatibility.
    Synchronization happens inside Docker containers.

    Args:
        device_id: GPU device ID (ignored, for compatibility)
    """
    # No-op: Synchronization happens in containers
    pass


def reset_peak_memory_stats(device_id: int = 0):
    """
    Reset peak memory statistics

    Note: This is a no-op placeholder for compatibility.
    Memory stats are managed inside Docker containers.

    Args:
        device_id: GPU device ID (ignored, for compatibility)
    """
    # No-op: Memory stats managed in containers
    pass


def get_memory_allocated(device_id: int = 0) -> float:
    """
    Get currently allocated GPU memory in bytes

    Args:
        device_id: GPU device ID

    Returns:
        float: Allocated memory in bytes, or 0 if unavailable
    """
    if not is_gpu_available():
        return 0.0

    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return float(info.used)
    except Exception as e:
        logger.warning(f"Failed to get memory allocated for GPU {device_id}: {e}")
        return 0.0


def get_memory_reserved(device_id: int = 0) -> float:
    """
    Get total reserved GPU memory in bytes

    Note: pynvml doesn't distinguish between allocated and reserved.
    Returns total used memory.

    Args:
        device_id: GPU device ID

    Returns:
        float: Reserved memory in bytes, or 0 if unavailable
    """
    # pynvml doesn't have separate "reserved" concept like PyTorch
    # Return total used memory as approximation
    return get_memory_allocated(device_id)


def get_max_memory_allocated(device_id: int = 0) -> float:
    """
    Get peak allocated GPU memory in bytes

    Note: pynvml doesn't track historical peak like PyTorch.
    Returns current usage as approximation.

    Args:
        device_id: GPU device ID

    Returns:
        float: Peak memory in bytes, or 0 if unavailable
    """
    # pynvml doesn't track peak memory like PyTorch
    # Return current usage as approximation
    return get_memory_allocated(device_id)


def ipc_collect():
    """
    Collect IPC (Inter-Process Communication) handles

    Note: This is a no-op placeholder for compatibility.
    IPC management happens inside Docker containers.
    """
    # No-op: IPC management happens in containers
    pass


# Context manager for automatic NVML initialization/shutdown
class NVMLContext:
    """Context manager for NVML initialization and cleanup"""

    def __enter__(self):
        initialize_nvml()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        shutdown_nvml()
        return False


__all__ = [
    'initialize_nvml',
    'shutdown_nvml',
    'is_gpu_available',
    'get_gpu_count',
    'empty_cache',
    'synchronize',
    'reset_peak_memory_stats',
    'get_memory_allocated',
    'get_memory_reserved',
    'get_max_memory_allocated',
    'ipc_collect',
    'NVMLContext',
    'PYNVML_AVAILABLE',
]
