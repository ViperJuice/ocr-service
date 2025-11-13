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
from .services.result_emitter import get_result_emitter
# GPU resource tracking removed - using container mode only
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting OCR Service API...")

    global file_manager, prompt_manager, job_manager, batch_manager, progress_emitter, model_manager, system_monitor
    settings = get_settings()

    logger.info("Starting in CONTAINER MODE - GPU management handled by containers")

    # Initialize services
    file_manager = FileManager(
        temp_directory=settings.api_temp_directory,
        expiry_hours=settings.temp_file_expiry_hours
    )

    prompt_manager = PromptManager(
        model_configs_path=settings.model_configs_path
    )

    # Initialize progress emitter for SSE streaming
    progress_emitter = ProgressEmitter()

    # Initialize result emitter for SSE streaming with event loop reference
    import asyncio
    loop = asyncio.get_running_loop()
    result_emitter = get_result_emitter()
    result_emitter._event_loop = loop  # Set the event loop for thread-safe operations
    logger.info(f"ResultEmitter configured with event loop: {loop}")

    job_manager = JobManager(
        processing_directory=settings.api_processing_directory,
        output_directory=settings.api_output_directory,
        max_concurrent_jobs=2,  # Limit concurrent jobs
        result_emitter=result_emitter
    )

    # Initialize batch manager
    batch_manager = BatchManager(
        processing_directory=settings.api_processing_directory,
        output_directory=settings.api_output_directory,
        max_concurrent_batches=1  # Process one batch at a time
    )

    # Initialize model manager (container mode only)
    from ..models.model_manager import ModelManager
    model_configs = settings.load_model_configs()
    model_manager = ModelManager(
        model_configs=model_configs['models']
    )

    # Initialize container mode
    logger.info("Initializing container mode...")
    await model_manager.initialize_container_mode(
        deepseek_url=settings.deepseek_container_url,
        qwen_url=settings.qwen_container_url,
        timeout=settings.container_timeout
    )
    logger.info("✓ Container mode initialized successfully")

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
        # Close container connections
        try:
            await model_manager.close_container_mode()
            logger.info("Container mode connections closed")
        except Exception as e:
            logger.error(f"Error closing container connections during shutdown: {e}")

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
