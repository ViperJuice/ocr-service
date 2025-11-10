"""GPU resource tracking for job scheduling."""
import threading
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class GPUResourceTracker:
    """
    Lightweight VRAM tracking for job scheduling.

    Does NOT replace HuggingFace's device_map or max_memory.
    Only tracks application-level job allocations to prevent
    concurrent jobs from over-allocating GPU memory.
    """

    def __init__(self, gpu_capacities_gb: Dict[int, float]):
        """
        Initialize GPU resource tracker.

        Args:
            gpu_capacities_gb: Dictionary mapping GPU ID to usable VRAM in GB.
                Example: {0: 22.0, 1: 22.0}  # 24GB - 2GB overhead
        """
        self.total_capacity = gpu_capacities_gb.copy()
        self.locks = {gpu_id: threading.Lock() for gpu_id in gpu_capacities_gb}
        self.allocations: Dict[int, Dict[str, float]] = {
            gpu_id: {} for gpu_id in gpu_capacities_gb
        }  # {gpu_id: {job_id: vram_gb}}

        logger.info(f"GPU Resource Tracker initialized with capacities: {gpu_capacities_gb}")

    def can_allocate(self, vram_requirements: Dict[int, float]) -> bool:
        """
        Check if VRAM is available without blocking.

        Args:
            vram_requirements: Dictionary mapping GPU ID to required VRAM in GB.
                Example: {0: 14.0, 1: 18.0}

        Returns:
            True if all GPUs have sufficient free VRAM, False otherwise.
        """
        for gpu_id, required_gb in vram_requirements.items():
            if gpu_id not in self.total_capacity:
                logger.warning(f"GPU {gpu_id} not in capacity map, cannot allocate")
                return False

            with self.locks[gpu_id]:
                used_gb = sum(self.allocations[gpu_id].values())
                available_gb = self.total_capacity[gpu_id] - used_gb

                if available_gb < required_gb:
                    logger.debug(
                        f"GPU {gpu_id}: Insufficient VRAM. "
                        f"Required: {required_gb:.1f}GB, Available: {available_gb:.1f}GB"
                    )
                    return False

        return True

    def acquire(self, vram_requirements: Dict[int, float], job_id: str) -> bool:
        """
        Reserve VRAM for a job. Non-blocking.

        Args:
            vram_requirements: Dictionary mapping GPU ID to required VRAM in GB.
            job_id: Unique job identifier.

        Returns:
            True if reservation successful, False if insufficient VRAM.
        """
        # First check if allocation is possible
        if not self.can_allocate(vram_requirements):
            return False

        # Acquire locks for all GPUs in order to prevent deadlock
        gpu_ids = sorted(vram_requirements.keys())
        acquired_locks = []

        try:
            # Acquire all locks
            for gpu_id in gpu_ids:
                self.locks[gpu_id].acquire()
                acquired_locks.append(gpu_id)

            # Double-check availability after acquiring locks
            for gpu_id, required_gb in vram_requirements.items():
                used_gb = sum(self.allocations[gpu_id].values())
                available_gb = self.total_capacity[gpu_id] - used_gb

                if available_gb < required_gb:
                    # Race condition: another thread allocated while we were acquiring locks
                    logger.debug(f"GPU {gpu_id}: VRAM no longer available after lock acquisition")
                    return False

            # All checks passed, record allocations
            for gpu_id, required_gb in vram_requirements.items():
                self.allocations[gpu_id][job_id] = required_gb

            logger.info(
                f"Acquired VRAM for job {job_id}: {vram_requirements}. "
                f"Status: {self._get_status_unlocked()}"
            )
            return True

        finally:
            # Release all acquired locks
            for gpu_id in reversed(acquired_locks):
                self.locks[gpu_id].release()

    def release(self, job_id: str):
        """
        Release all VRAM reserved by a job.

        Args:
            job_id: Job identifier whose resources should be released.
        """
        released = {}

        # Release from all GPUs
        for gpu_id in self.allocations:
            with self.locks[gpu_id]:
                if job_id in self.allocations[gpu_id]:
                    released[gpu_id] = self.allocations[gpu_id][job_id]
                    del self.allocations[gpu_id][job_id]

        if released:
            logger.info(f"Released VRAM for job {job_id}: {released}")
        else:
            logger.warning(f"No VRAM allocation found for job {job_id}")

    def get_status(self) -> Dict:
        """
        Get current VRAM usage per GPU (thread-safe).

        Returns:
            Dictionary with per-GPU status information.
        """
        status = {}

        for gpu_id in self.total_capacity:
            with self.locks[gpu_id]:
                used_gb = sum(self.allocations[gpu_id].values())
                status[gpu_id] = {
                    "total_gb": self.total_capacity[gpu_id],
                    "used_gb": used_gb,
                    "available_gb": self.total_capacity[gpu_id] - used_gb,
                    "active_jobs": list(self.allocations[gpu_id].keys())
                }

        return status

    def _get_status_unlocked(self) -> Dict:
        """Get status without acquiring locks (internal use only)."""
        status = {}
        for gpu_id in self.total_capacity:
            used_gb = sum(self.allocations[gpu_id].values())
            status[gpu_id] = {
                "used_gb": used_gb,
                "available_gb": self.total_capacity[gpu_id] - used_gb
            }
        return status
