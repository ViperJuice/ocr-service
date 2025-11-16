"""System monitoring for tracking resource usage during PDF processing."""

import json
import threading
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import deque
import psutil

logger = logging.getLogger(__name__)

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False
    logger.warning("pynvml not available, GPU monitoring disabled")

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.info("torch not available, additional GPU metrics disabled")


class SystemMonitor:
    """Monitor system resources during PDF processing with stage support."""

    def __init__(self, output_path: Path, interval: int = 30, job_id: Optional[str] = None):
        """
        Initialize system monitor.

        Args:
            output_path: Path to write monitoring log (will use .syslog.jsonl extension)
            interval: Monitoring interval in seconds (default: 30)
            job_id: Optional job ID for API correlation
        """
        self.output_path = Path(output_path).with_suffix('.syslog.jsonl')
        self.interval = interval
        self.job_id = job_id
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.process = psutil.Process()

        # Stage-aware tracking
        self.active_stage: Optional[str] = None
        self.stage_total_pages: Optional[int] = None
        self.stage_page: int = 0
        self.overall_progress_pct: Optional[float] = None
        self.loaded_models: List[str] = []

        # Model tracking
        self.model_type: Optional[str] = None
        self.model_id: Optional[str] = None
        self.device_map: Optional[Dict[str, Any]] = None
        self.is_sharded: bool = False
        self.gpu_assignment: List[int] = []

        # Per-page timing
        self.page_start_time: Optional[float] = None
        self.current_page_duration: Optional[float] = None

        # Memory tracking (for delta calculation)
        self.previous_memory: Dict[int, Dict[str, float]] = {}

        # Metrics buffer for API access (last 60 seconds)
        self._metrics_buffer = deque(maxlen=60)
        self._buffer_lock = threading.Lock()

        # Initialize NVML for GPU monitoring
        self.gpu_available = False
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self.gpu_count = pynvml.nvmlDeviceGetCount()
                self.gpu_handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(self.gpu_count)]
                self.gpu_available = True
                logger.info(f"GPU monitoring enabled for {self.gpu_count} GPUs")
            except pynvml.NVMLError as e:
                logger.warning(f"Failed to initialize NVML: {e}")
                self.gpu_available = False

    def start(self) -> None:
        """Start monitoring in background thread."""
        if self.running:
            logger.warning("Monitor already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info(f"System monitoring started (interval: {self.interval}s, log: {self.output_path})")

    def stop(self) -> None:
        """Stop monitoring thread."""
        if not self.running:
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("System monitoring stopped")

        # Cleanup NVML
        if self.gpu_available:
            try:
                pynvml.nvmlShutdown()
            except pynvml.NVMLError:
                pass


    def _monitor_loop(self) -> None:
        """Main monitoring loop (runs in background thread)."""
        while self.running:
            try:
                metrics = self._collect_metrics()
                self._write_metrics(metrics)
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")

            # Sleep in small intervals to allow quick shutdown
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

    def _collect_metrics(self) -> Dict[str, Any]:
        """
        Collect current system metrics.

        Returns:
            Dict of metrics
        """
        metrics = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }

        # Add job_id if available
        if self.job_id:
            metrics['job_id'] = self.job_id

        # Add stage-aware metrics if available
        if self.active_stage is not None:
            metrics['active_stage'] = self.active_stage
            metrics['stage_page'] = self.stage_page
            metrics['stage_total_pages'] = self.stage_total_pages

            if self.stage_total_pages and self.stage_total_pages > 0:
                metrics['stage_progress_pct'] = round(
                    (self.stage_page + 1) / self.stage_total_pages * 100, 1
                )

            if self.overall_progress_pct is not None:
                metrics['overall_progress_pct'] = round(self.overall_progress_pct, 1)

            if self.loaded_models:
                metrics['loaded_models'] = self.loaded_models

        # Add model tracking
        if self.model_type is not None:
            metrics['model_type'] = self.model_type
        if self.model_id is not None:
            metrics['model_id'] = self.model_id
        if self.is_sharded:
            metrics['is_sharded'] = self.is_sharded
        if self.gpu_assignment:
            metrics['gpu_assignment'] = self.gpu_assignment
        if self.device_map is not None:
            # Simplify device_map for logging (just show GPU assignments, not all layers)
            metrics['device_map_summary'] = self._summarize_device_map(self.device_map)

        # Add per-page timing (calculate dynamically from start time)
        if self.page_start_time is not None:
            metrics['page_start_time'] = self.page_start_time
            # Calculate current duration dynamically
            current_duration = time.time() - self.page_start_time
            metrics['current_page_duration_s'] = round(current_duration, 2)

        # Process metrics
        try:
            with self.process.oneshot():
                process_info = self.process.memory_info()
                metrics['process'] = {
                    'rss_mb': round(process_info.rss / 1024 / 1024, 1),
                    'vms_mb': round(process_info.vms / 1024 / 1024, 1),
                    'cpu_percent': round(self.process.cpu_percent(), 1)
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"Failed to get process metrics: {e}")

        # System metrics
        try:
            metrics['system'] = {
                'ram_available_mb': round(psutil.virtual_memory().available / 1024 / 1024, 1),
                'ram_percent': round(psutil.virtual_memory().percent, 1),
                'cpu_percent': round(psutil.cpu_percent(interval=0.1), 1)
            }
        except Exception as e:
            logger.warning(f"Failed to get system metrics: {e}")

        # GPU metrics with enhanced memory tracking
        if self.gpu_available:
            try:
                metrics['gpus'] = []
                for i, handle in enumerate(self.gpu_handles):
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)

                    try:
                        temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    except pynvml.NVMLError:
                        temperature = None

                    gpu_metrics = {
                        'id': i,
                        'memory_used_mb': round(mem_info.used / 1024 / 1024, 1),
                        'memory_total_mb': round(mem_info.total / 1024 / 1024, 1),
                        'memory_percent': round((mem_info.used / mem_info.total) * 100, 1),
                        'utilization_percent': utilization.gpu,
                    }

                    if temperature is not None:
                        gpu_metrics['temperature_c'] = temperature

                    # Enhanced PyTorch memory tracking
                    if TORCH_AVAILABLE and torch.cuda.is_available() and i < torch.cuda.device_count():
                        try:
                            device = torch.device(f'cuda:{i}')
                            allocated_mb = round(torch.cuda.memory_allocated(device) / 1024 / 1024, 1)
                            reserved_mb = round(torch.cuda.memory_reserved(device) / 1024 / 1024, 1)
                            peak_mb = round(torch.cuda.max_memory_allocated(device) / 1024 / 1024, 1)

                            gpu_metrics['torch_allocated_mb'] = allocated_mb
                            gpu_metrics['torch_reserved_mb'] = reserved_mb
                            gpu_metrics['torch_peak_mb'] = peak_mb

                            # KV cache estimate (reserved - allocated)
                            kv_cache_estimate = max(0, reserved_mb - allocated_mb)
                            gpu_metrics['kv_cache_estimate_mb'] = round(kv_cache_estimate, 1)

                            # Memory delta (spike detection)
                            if i in self.previous_memory:
                                prev_allocated = self.previous_memory[i].get('allocated', allocated_mb)
                                delta = allocated_mb - prev_allocated
                                gpu_metrics['memory_delta_mb'] = round(delta, 1)

                            # Store current for next iteration
                            self.previous_memory[i] = {'allocated': allocated_mb}

                        except Exception as e:
                            logger.warning(f"Failed to get PyTorch metrics for GPU {i}: {e}")

                    metrics['gpus'].append(gpu_metrics)

            except pynvml.NVMLError as e:
                logger.warning(f"Failed to get GPU metrics: {e}")

        return metrics

    def _write_metrics(self, metrics: Dict[str, Any]) -> None:
        """
        Write metrics to log file and buffer for API access.

        Args:
            metrics: Metrics dict to write
        """
        try:
            # Write to file
            with open(self.output_path, 'a') as f:
                f.write(json.dumps(metrics) + '\n')
                f.flush()

            # Also buffer for API access
            with self._buffer_lock:
                self._metrics_buffer.append(metrics)
        except IOError as e:
            logger.error(f"Failed to write metrics: {e}")

    def set_model_info(
        self,
        model_type: str,
        model_id: str,
        device_map: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Set information about the currently loaded model.

        Args:
            model_type: Model type name (e.g., "deepseek-ocr", "qwen3-vl-8b")
            model_id: HuggingFace model ID
            device_map: Device map showing layer->GPU assignments
        """
        self.model_type = model_type
        self.model_id = model_id
        self.device_map = device_map

        # Determine if sharded and which GPUs
        if device_map:
            # Extract unique devices from device_map
            if isinstance(device_map, dict):
                devices = set()
                for device in device_map.values():
                    if isinstance(device, int):
                        devices.add(device)
                    elif isinstance(device, str):
                        # Handle "cuda:0", "cuda:1", etc.
                        if device.startswith('cuda:'):
                            try:
                                devices.add(int(device.split(':')[1]))
                            except (IndexError, ValueError):
                                pass
                        elif device.isdigit():
                            devices.add(int(device))

                self.gpu_assignment = sorted(list(devices))
                self.is_sharded = len(devices) > 1
            else:
                self.is_sharded = False
                self.gpu_assignment = []
        else:
            self.is_sharded = False
            self.gpu_assignment = []

        logger.info(
            f"Model info set: {model_type} ({model_id}), "
            f"Sharded: {self.is_sharded}, GPUs: {self.gpu_assignment}"
        )

    def update_page_timing(self, page_start_time: float) -> None:
        """
        Update timing for current page.

        Args:
            page_start_time: Unix timestamp when page processing started
        """
        self.page_start_time = page_start_time

    def _summarize_device_map(self, device_map: Dict[str, Any]) -> Dict[str, int]:
        """
        Summarize device map to show GPU assignments without all layer details.

        Args:
            device_map: Full device map from model

        Returns:
            Simplified map showing GPU -> layer count
        """
        summary = {}
        for layer, device in device_map.items():
            device_str = str(device)
            if device_str not in summary:
                summary[device_str] = 0
            summary[device_str] += 1
        return summary

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    def get_recent_metrics(self, seconds: int = 60) -> List[dict]:
        """
        Get buffered metrics for the last N seconds.

        Args:
            seconds: Number of seconds to retrieve (max: len of buffer)

        Returns:
            List of metric dictionaries, oldest to newest
        """
        with self._buffer_lock:
            # Return last N entries (or all if buffer smaller)
            return list(self._metrics_buffer)[-seconds:]

    def get_current_system_metrics(self) -> dict:
        """
        Get current system-wide metrics snapshot.

        Returns:
            Dictionary with GPU, CPU, RAM metrics
        """
        metrics = {
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "gpus": []
        }

        # Get RAM metrics
        mem = psutil.virtual_memory()
        metrics["ram_used_gb"] = (mem.total - mem.available) / (1024**3)
        metrics["ram_total_gb"] = mem.total / (1024**3)
        metrics["ram_percent"] = mem.percent

        # Get GPU metrics
        if self.gpu_available and NVML_AVAILABLE:
            try:
                for i in range(self.gpu_count):
                    handle = self.gpu_handles[i]
                    name = pynvml.nvmlDeviceGetName(handle)
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)

                    metrics["gpus"].append({
                        "id": i,
                        "name": name.decode('utf-8') if isinstance(name, bytes) else name,
                        "memory_used_mb": mem_info.used // (1024**2),
                        "memory_total_mb": mem_info.total // (1024**2),
                        "memory_percent": mem_info.used / mem_info.total,
                        "utilization_percent": utilization.gpu,
                        "temperature_c": temperature
                    })
            except Exception as e:
                logger.warning(f"Failed to get GPU metrics: {e}")

        return metrics

    # ========== Stage-Aware Methods (New) ==========

    def set_active_stage(
        self,
        stage_name: str,
        stage_total_pages: int,
        loaded_models: List[str]
    ) -> None:
        """
        Set the currently active pipeline stage.

        Args:
            stage_name: "ocr" or "merge"
            stage_total_pages: Total pages for this stage
            loaded_models: List of loaded model names
        """
        self.active_stage = stage_name
        self.stage_total_pages = stage_total_pages
        self.stage_page = 0
        self.loaded_models = loaded_models
        logger.info(f"System monitor tracking stage: {stage_name} ({stage_total_pages} pages)")

    def update_stage_progress(
        self,
        stage_page: int,
        overall_progress_pct: Optional[float] = None
    ) -> None:
        """
        Update progress within current stage.

        Args:
            stage_page: Current page within stage (0-indexed)
            overall_progress_pct: Optional overall progress (0-100)
        """
        self.stage_page = stage_page
        if overall_progress_pct is not None:
            self.overall_progress_pct = overall_progress_pct

    def log_stage_transition(
        self,
        from_stage: Optional[str],
        to_stage: str,
        transition_metadata: Optional[Dict] = None
    ) -> None:
        """
        Log a stage transition event.

        Args:
            from_stage: Previous stage ("ocr" or None if starting)
            to_stage: Next stage ("merge" or "completed")
            transition_metadata: Optional metadata (stage1_duration, etc.)
        """
        transition_event = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'event_type': 'stage_transition',
            'from_stage': from_stage,
            'to_stage': to_stage
        }

        if transition_metadata:
            transition_event['metadata'] = transition_metadata

        # Write special log entry
        try:
            with open(self.output_path, 'a') as f:
                f.write(json.dumps(transition_event) + '\n')
                f.flush()
            logger.info(f"Stage transition: {from_stage} -> {to_stage}")
        except IOError as e:
            logger.error(f"Failed to log stage transition: {e}")

    def log_page_completion(
        self,
        page_number: int,
        stage: str,
        page_duration: float,
        page_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log page completion event with detailed metrics.

        Args:
            page_number: Page number (1-indexed)
            stage: Processing stage ("ocr" or "merge")
            page_duration: Total processing time for page in seconds
            page_metadata: Optional metadata from OCRResult or processing
        """
        completion_event = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'event_type': 'page_completion',
            'stage': stage,
            'page_number': page_number,
            'page_duration_s': round(page_duration, 2)
        }

        # Add model information
        if self.model_type:
            completion_event['model_type'] = self.model_type
        if self.model_id:
            completion_event['model_id'] = self.model_id
        if self.is_sharded:
            completion_event['is_sharded'] = self.is_sharded
        if self.gpu_assignment:
            completion_event['gpu_assignment'] = self.gpu_assignment

        # Add page metadata if provided
        if page_metadata:
            # Extract DeepSeek OCR specific metrics
            if 'image_size' in page_metadata:
                completion_event['image_size'] = page_metadata['image_size']

            if 'infer_config' in page_metadata:
                infer_config = page_metadata['infer_config']
                completion_event['base_size'] = infer_config.get('base_size')
                completion_event['image_size_config'] = infer_config.get('image_size')
                completion_event['crop_mode'] = infer_config.get('crop_mode')

            if 'resolution_mode' in page_metadata:
                completion_event['resolution_mode'] = page_metadata['resolution_mode']

            if 'memory_usage' in page_metadata:
                completion_event['memory_usage'] = page_metadata['memory_usage']

            # Calculate text metrics
            if 'text' in page_metadata:
                text = page_metadata['text']
                completion_event['output_text_length'] = len(text)

                # Estimate vision tokens based on resolution mode
                resolution_mode = page_metadata.get('resolution_mode', 'unknown')
                vision_tokens_map = {
                    'tiny': 64,
                    'small': 100,
                    'base': 256,
                    'large': 400,
                    'gundam': 256,  # Base estimate for gundam
                    'gundam-m': 400
                }
                vision_tokens = vision_tokens_map.get(resolution_mode, 256)
                completion_event['estimated_vision_tokens'] = vision_tokens

                # Estimate compression ratio (rough approximation using character count / 4 as token estimate)
                estimated_text_tokens = max(1, len(text) // 4)
                compression_ratio = estimated_text_tokens / vision_tokens if vision_tokens > 0 else 0
                completion_event['estimated_compression_ratio'] = round(compression_ratio, 2)

        # Add GPU memory snapshot at completion
        if self.gpu_available and TORCH_AVAILABLE:
            try:
                gpu_snapshot = {}
                for i in range(self.gpu_count):
                    if torch.cuda.is_available() and i < torch.cuda.device_count():
                        device = torch.device(f'cuda:{i}')
                        gpu_snapshot[f'gpu_{i}_allocated_mb'] = round(
                            torch.cuda.memory_allocated(device) / 1024 / 1024, 1
                        )
                        gpu_snapshot[f'gpu_{i}_reserved_mb'] = round(
                            torch.cuda.memory_reserved(device) / 1024 / 1024, 1
                        )
                        gpu_snapshot[f'gpu_{i}_peak_mb'] = round(
                            torch.cuda.max_memory_allocated(device) / 1024 / 1024, 1
                        )

                if gpu_snapshot:
                    completion_event['memory_snapshot'] = gpu_snapshot
            except Exception as e:
                logger.warning(f"Failed to capture GPU snapshot for page completion: {e}")

        # Write page completion event
        try:
            with open(self.output_path, 'a') as f:
                f.write(json.dumps(completion_event) + '\n')
                f.flush()
            logger.debug(f"Page completion logged: {stage} page {page_number} ({page_duration:.1f}s)")
        except IOError as e:
            logger.error(f"Failed to log page completion: {e}")
