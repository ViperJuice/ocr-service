"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from pathlib import Path

from config.settings import get_settings
from .services import FileManager, PromptManager, JobManager, BatchManager, ProgressEmitter
from .services.gpu_resource_tracker import GPUResourceTracker
from .services.capability_detector import CapabilityDetector
from ..utils.system_monitor import SystemMonitor
from .middleware import (
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)
from . import processing_routes, config_routes, file_routes, monitoring_routes, batch_routes

logger = logging.getLogger(__name__)

# Global service instances
file_manager: FileManager = None
prompt_manager: PromptManager = None
job_manager: JobManager = None
batch_manager: BatchManager = None
progress_emitter: ProgressEmitter = None
model_manager = None
system_monitor: SystemMonitor = None
gpu_tracker: GPUResourceTracker = None
system_capability: dict = None  # Detected system capability tier


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting OCR Service API...")

    global file_manager, prompt_manager, job_manager, batch_manager, progress_emitter, model_manager, system_monitor, gpu_tracker, system_capability
    settings = get_settings()

    # Initialize GPU resource tracker and detect system capabilities
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            # Reserve 2GB per GPU for overhead (CUDA context, PyTorch, etc.)
            gpu_capacities = {}
            for gpu_id in range(gpu_count):
                total_vram_bytes = torch.cuda.get_device_properties(gpu_id).total_memory
                total_vram_gb = total_vram_bytes / (1024 ** 3)
                usable_vram_gb = total_vram_gb - 2.0  # 2GB overhead
                gpu_capacities[gpu_id] = usable_vram_gb
                logger.info(
                    f"GPU {gpu_id} ({torch.cuda.get_device_name(gpu_id)}): "
                    f"Total: {total_vram_gb:.1f}GB, Usable: {usable_vram_gb:.1f}GB"
                )

            # Detect maximum quality tier system can support
            max_tier, tier_info = CapabilityDetector.detect_max_tier(gpu_capacities)
            system_capability = {
                "max_tier": max_tier,
                "tier_info": tier_info,
                "gpu_count": gpu_count,
                "gpu_capacities": gpu_capacities
            }

            logger.info(
                f"System capability: Tier {max_tier} ({tier_info['description']}) - "
                f"ALL JOBS WILL RUN AT TIER {max_tier} (Quality-First Policy)"
            )

            gpu_tracker = GPUResourceTracker(gpu_capacities_gb=gpu_capacities)
            logger.info(f"GPU resource tracking enabled for {gpu_count} GPU(s)")
        else:
            logger.warning("CUDA not available - GPU resource tracking disabled")
            gpu_tracker = None
            system_capability = {
                "max_tier": 5,
                "tier_info": {"tier": 5, "description": "CPU fallback"},
                "gpu_count": 0,
                "gpu_capacities": {}
            }
    except Exception as e:
        logger.error(f"Failed to initialize GPU resource tracker: {e}")
        gpu_tracker = None
        system_capability = None

    # Initialize services
    file_manager = FileManager(
        temp_directory=settings.api_temp_directory,
        expiry_hours=settings.temp_file_expiry_hours
    )

    prompt_manager = PromptManager(
        model_configs_path=settings.model_configs_path
    )

    job_manager = JobManager(
        processing_directory=settings.api_processing_directory,
        output_directory=settings.api_output_directory,
        max_concurrent_jobs=2,  # Limit concurrent jobs due to GPU memory
        gpu_tracker=gpu_tracker,
        system_capability=system_capability
    )

    # Initialize progress emitter for SSE streaming
    progress_emitter = ProgressEmitter()

    # Initialize batch manager
    batch_manager = BatchManager(
        processing_directory=settings.api_processing_directory,
        output_directory=settings.api_output_directory,
        max_concurrent_batches=1  # Process one batch at a time
    )

    # Initialize model manager (lazy loading)
    from ..models.model_manager import ModelManager
    model_configs = settings.load_model_configs()
    model_manager = ModelManager(model_configs=model_configs['models'])

    # Initialize global system monitor for API
    system_monitor = SystemMonitor(
        output_path=Path(settings.api_output_directory) / "api_system_monitor.syslog",
        interval=1,  # 1 second for real-time monitoring
        job_id="api_global"
    )
    system_monitor.start()

    # Set managers in route modules
    processing_routes.set_managers(file_manager, prompt_manager, job_manager, model_manager)
    config_routes.set_prompt_manager(prompt_manager)
    file_routes.set_file_manager(file_manager)
    monitoring_routes.set_managers(system_monitor, job_manager, model_manager)
    batch_routes.set_managers(batch_manager, file_manager, job_manager, prompt_manager, model_manager, progress_emitter)

    logger.info("OCR Service API started successfully")

    yield

    # Shutdown
    logger.info("Shutting down OCR Service API...")

    # Stop system monitor
    if system_monitor:
        system_monitor.stop()

    # Cleanup resources
    if model_manager:
        # Unload any loaded models
        try:
            if model_manager.current_model_name:
                model_manager.unload_model(model_manager.current_model_name)
        except Exception as e:
            logger.error(f"Error unloading model during shutdown: {e}")

    logger.info("OCR Service API shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    settings = get_settings()

    app = FastAPI(
        title="OCR Service API",
        description="Production-ready OCR service using vision-language models",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS
    if settings.enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Register exception handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    # Include routers
    app.include_router(processing_routes.router)
    app.include_router(config_routes.router)
    app.include_router(file_routes.router)
    app.include_router(monitoring_routes.router)
    app.include_router(batch_routes.router)

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "ocr-service"}

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "service": "OCR Service API",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health"
        }

    return app


# Create app instance
app = create_app()
