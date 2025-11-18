"""Monitoring service for real-time system metrics."""
import json
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import httpx

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service for reading and serving system monitoring metrics."""

    def __init__(self, output_directory: Path = None):
        """
        Initialize monitoring service.

        Args:
            output_directory: Directory where .syslog.jsonl files are stored
        """
        if output_directory is None:
            output_directory = Path("data/output")
        self.output_directory = Path(output_directory)

    def get_latest_metrics(self, job_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get the most recent metrics snapshot.

        Args:
            job_id: Optional job identifier (filename without extension)

        Returns:
            Latest metrics dict or None if no metrics found
        """
        log_file = self._find_log_file(job_id)
        if not log_file:
            return None

        try:
            with open(log_file, 'r') as f:
                # Read last non-empty line
                lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if line:
                        return json.loads(line)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read metrics from {log_file}: {e}")
            return None

        return None

    def get_metrics_history(
        self,
        job_id: Optional[str] = None,
        minutes: int = 60,
        event_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical metrics for the specified time window.

        Args:
            job_id: Optional job identifier
            minutes: Time window in minutes (default: 60)
            event_type: Optional filter by event_type (e.g., "stage_transition")

        Returns:
            List of metrics dicts
        """
        log_file = self._find_log_file(job_id)
        if not log_file:
            return []

        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        metrics = []

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        metric = json.loads(line)

                        # Filter by time
                        timestamp_str = metric.get('timestamp', '')
                        if timestamp_str:
                            # Parse ISO format timestamp
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            if timestamp < cutoff_time:
                                continue

                        # Filter by event type if specified
                        if event_type and metric.get('event_type') != event_type:
                            continue

                        metrics.append(metric)
                    except json.JSONDecodeError:
                        continue

        except IOError as e:
            logger.error(f"Failed to read metrics history from {log_file}: {e}")

        return metrics

    def get_active_jobs(self) -> List[str]:
        """
        Get list of active jobs (based on .syslog.jsonl files).

        Returns:
            List of job IDs
        """
        pattern = str(self.output_directory / "*.syslog.jsonl")
        log_files = glob.glob(pattern)

        job_ids = []
        for log_file in log_files:
            # Extract job ID from filename (without .syslog.jsonl extension)
            filename = Path(log_file).name
            if filename.endswith('.syslog.jsonl'):
                job_id = filename[:-13]  # Remove .syslog.jsonl
                job_ids.append(job_id)

        return sorted(job_ids)

    def get_job_summary(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get summary information for a job.

        Args:
            job_id: Job identifier

        Returns:
            Summary dict with job info
        """
        log_file = self._find_log_file(job_id)
        if not log_file:
            return None

        # Read first and last metrics
        first_metric = None
        last_metric = None
        stage_transitions = []

        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()

                # Get first metric
                for line in lines:
                    line = line.strip()
                    if line:
                        try:
                            first_metric = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue

                # Get last metric and stage transitions
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        metric = json.loads(line)
                        if last_metric is None:
                            last_metric = metric

                        if metric.get('event_type') == 'stage_transition':
                            stage_transitions.insert(0, metric)
                    except json.JSONDecodeError:
                        continue

        except IOError as e:
            logger.error(f"Failed to read job summary from {log_file}: {e}")
            return None

        if not first_metric or not last_metric:
            return None

        # Calculate duration
        start_time = datetime.fromisoformat(first_metric['timestamp'].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(last_metric['timestamp'].replace('Z', '+00:00'))
        duration_seconds = (end_time - start_time).total_seconds()

        return {
            'job_id': job_id,
            'start_time': first_metric['timestamp'],
            'last_update': last_metric['timestamp'],
            'duration_seconds': round(duration_seconds, 1),
            'active_stage': last_metric.get('active_stage'),
            'stage_page': last_metric.get('stage_page'),
            'stage_total_pages': last_metric.get('stage_total_pages'),
            'overall_progress_pct': last_metric.get('overall_progress_pct'),
            'stage_transitions': stage_transitions,
            'model_type': last_metric.get('model_type'),
            'is_sharded': last_metric.get('is_sharded', False),
            'gpu_assignment': last_metric.get('gpu_assignment', [])
        }

    def get_page_completions(
        self,
        job_id: Optional[str] = None,
        stage: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all page completion events.

        Args:
            job_id: Optional job identifier
            stage: Optional filter by stage ("ocr" or "merge")

        Returns:
            List of page completion events
        """
        log_file = self._find_log_file(job_id)
        if not log_file:
            return []

        page_completions = []

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)

                        # Filter for page_completion events
                        if entry.get('event_type') != 'page_completion':
                            continue

                        # Filter by stage if specified
                        if stage and entry.get('stage') != stage:
                            continue

                        page_completions.append(entry)
                    except json.JSONDecodeError:
                        continue

        except IOError as e:
            logger.error(f"Failed to read page completions from {log_file}: {e}")

        return page_completions

    def _find_log_file(self, job_id: Optional[str] = None) -> Optional[Path]:
        """
        Find the log file for a job.

        Args:
            job_id: Optional job identifier. If None, returns most recent log file.

        Returns:
            Path to log file or None if not found
        """
        pattern = str(self.output_directory / "*.syslog.jsonl")
        log_files = glob.glob(pattern)

        if not log_files:
            return None

        if job_id:
            # Look for specific job
            target_file = self.output_directory / f"{job_id}.syslog.jsonl"
            if target_file.exists():
                return target_file
            return None
        else:
            # Return most recently modified file
            log_files.sort(key=lambda x: Path(x).stat().st_mtime, reverse=True)
            return Path(log_files[0])

    async def _fetch_container_info(self, url: str, container_name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch info from a container endpoint.

        Args:
            url: Container /info endpoint URL
            container_name: Name for logging (e.g., "deepseek", "qwen")

        Returns:
            Container info dict or None if unavailable
        """
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"{container_name} container returned status {response.status_code}")
        except httpx.ConnectError:
            logger.debug(f"{container_name} container not reachable at {url}")
        except Exception as e:
            logger.warning(f"Failed to fetch {container_name} container info: {e}")
        return None

    async def get_system_metrics_async(
        self,
        system_monitor,
        job_manager,
        model_manager=None,
        deepseek_url: str = "http://localhost:8001",
        qwen_url: str = "http://localhost:8002"
    ) -> dict:
        """
        Get current system-wide metrics including container info.

        Args:
            system_monitor: SystemMonitor instance
            job_manager: JobManager instance
            model_manager: ModelManager instance (optional)
            deepseek_url: DeepSeek container base URL
            qwen_url: Qwen container base URL

        Returns:
            Dictionary with complete system metrics
        """
        # Get base system metrics
        metrics = system_monitor.get_current_system_metrics()

        # Add queue stats
        metrics["queue"] = job_manager.get_queue_stats()

        # Add active model info if available
        if model_manager and hasattr(model_manager, 'current_model'):
            model = model_manager.current_model
            if model:
                metrics["active_model"] = {
                    "model_id": getattr(model, 'model_id', 'unknown'),
                    "load_time_seconds": getattr(model, '_load_time', 0.0),
                    "memory_footprint_gb": getattr(model, '_memory_footprint', 0.0)
                }

        # PHASE 4: DeepSeek params retrieval disabled (database-only mode)
        # TODO: Query database for active processing jobs instead of in-memory dict
        # active_jobs = [j for j in job_manager.jobs.values()
        #                if j.status.value == "PROCESSING"]
        # if active_jobs:
        #     job = active_jobs[0]
        #     if job.processing_options:
        #         metrics["deepseek_params"] = {
        #             "dpi": job.processing_options.get("dpi", 300),
        #             "resolution_mode": "quality" if job.processing_options.get("prefer_quality") else "standard",
        #             "image_width": job.processing_options.get("image_width", 0),
        #             "image_height": job.processing_options.get("image_height", 0)
        #         }

        # Fetch container metrics
        containers = {}

        # Fetch DeepSeek info
        deepseek_info = await self._fetch_container_info(f"{deepseek_url}/info", "deepseek")
        if deepseek_info:
            containers["deepseek"] = {
                "status": "loaded" if deepseek_info.get("model_loaded") else "unloaded",
                "model": deepseek_info.get("model_id"),
                "gpu_ids": deepseek_info.get("gpu_ids", []),
                "available": True
            }
        else:
            containers["deepseek"] = {"status": "unavailable", "available": False}

        # Fetch Qwen info
        qwen_info = await self._fetch_container_info(f"{qwen_url}/info", "qwen")
        if qwen_info:
            containers["qwen"] = {
                "status": "loaded" if qwen_info.get("model_loaded") else "unloaded",
                "model": qwen_info.get("model_id"),
                "gpu_ids": qwen_info.get("gpu_ids", []),
                "available": True
            }
        else:
            containers["qwen"] = {"status": "unavailable", "available": False}

        metrics["containers"] = containers

        return metrics

    def get_system_metrics(
        self,
        system_monitor,
        job_manager,
        model_manager=None
    ) -> dict:
        """
        Get current system-wide metrics (synchronous wrapper).

        Args:
            system_monitor: SystemMonitor instance
            job_manager: JobManager instance
            model_manager: ModelManager instance (optional)

        Returns:
            Dictionary with complete system metrics
        """
        # Get base system metrics
        metrics = system_monitor.get_current_system_metrics()

        # Add queue stats
        metrics["queue"] = job_manager.get_queue_stats()

        # Add active model info if available
        if model_manager and hasattr(model_manager, 'current_model'):
            model = model_manager.current_model
            if model:
                metrics["active_model"] = {
                    "model_id": getattr(model, 'model_id', 'unknown'),
                    "load_time_seconds": getattr(model, '_load_time', 0.0),
                    "memory_footprint_gb": getattr(model, '_memory_footprint', 0.0)
                }

        # PHASE 4: DeepSeek params retrieval disabled (database-only mode)
        # TODO: Query database for active processing jobs instead of in-memory dict
        # active_jobs = [j for j in job_manager.jobs.values()
        #                if j.status.value == "PROCESSING"]
        # if active_jobs:
        #     job = active_jobs[0]
        #     if job.processing_options:
        #         metrics["deepseek_params"] = {
        #             "dpi": job.processing_options.get("dpi", 300),
        #             "resolution_mode": "quality" if job.processing_options.get("prefer_quality") else "standard",
        #             "image_width": job.processing_options.get("image_width", 0),
        #             "image_height": job.processing_options.get("image_height", 0)
        #         }

        return metrics

    def get_system_metrics_history(
        self,
        system_monitor,
        seconds: int = 60
    ) -> dict:
        """
        Get historical system metrics.

        Args:
            system_monitor: SystemMonitor instance
            seconds: Number of seconds of history to retrieve

        Returns:
            Dictionary with metrics array and time range
        """
        metrics = system_monitor.get_recent_metrics(seconds)

        if not metrics:
            return {
                "metrics": [],
                "time_range": {
                    "start": None,
                    "end": None,
                    "duration_seconds": 0
                }
            }

        return {
            "metrics": metrics,
            "time_range": {
                "start": metrics[0]["timestamp"] if metrics else None,
                "end": metrics[-1]["timestamp"] if metrics else None,
                "duration_seconds": len(metrics)
            }
        }
