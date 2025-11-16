"""
Direct test of container orchestration to verify it works independently.
"""
import asyncio
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Test container orchestrator directly."""
    from src.services.container_orchestrator import ContainerOrchestrator, ContainerName
    from src.preprocessing.pipeline_coordinator import PipelineCoordinator, StageTransitionEvent, PipelineStage

    # Get event loop
    loop = asyncio.get_running_loop()

    # Create container orchestrator
    orchestrator = ContainerOrchestrator(
        compose_file="/home/jenner/code/ocr-service/docker-compose.yml",
        enabled=True,
        event_loop=loop
    )

    logger.info("Container orchestrator created")
    logger.info(f"Orchestrator enabled: {orchestrator.is_enabled()}")

    # Create pipeline coordinator
    coordinator = PipelineCoordinator(
        container_orchestrator=orchestrator,
        job_id="test-job-001",  # Dummy job ID for testing
        result_emitter=None,
        event_loop=loop
    )

    logger.info("Pipeline coordinator created")

    # Test pipeline start (should start DeepSeek container)
    logger.info("\n" + "="*80)
    logger.info("TEST 1: Pipeline start (should start DeepSeek container)")
    logger.info("="*80)

    start_event = StageTransitionEvent(
        from_stage=None,
        to_stage=PipelineStage.INIT,
        timestamp=asyncio.get_event_loop().time()
    )

    try:
        await coordinator.on_pipeline_start(start_event)
        logger.info("✓ Pipeline start completed successfully")
    except Exception as e:
        logger.error(f"✗ Pipeline start failed: {e}", exc_info=True)
        return

    # Check container states
    states = coordinator.get_container_states()
    logger.info(f"Container states: {states}")

    # Wait a bit to let things settle
    await asyncio.sleep(2)

    # Test OCR complete transition (should stop DeepSeek, start Qwen)
    logger.info("\n" + "="*80)
    logger.info("TEST 2: OCR complete (should stop DeepSeek, start Qwen)")
    logger.info("="*80)

    ocr_complete_event = StageTransitionEvent(
        from_stage=PipelineStage.OCR,
        to_stage=PipelineStage.MERGE,
        timestamp=asyncio.get_event_loop().time()
    )

    try:
        await coordinator.on_ocr_complete(ocr_complete_event)
        logger.info("✓ OCR complete transition succeeded")
    except Exception as e:
        logger.error(f"✗ OCR complete transition failed: {e}", exc_info=True)
        return

    # Check container states
    states = coordinator.get_container_states()
    logger.info(f"Container states: {states}")

    # Wait a bit
    await asyncio.sleep(2)

    # Test pipeline complete (should stop Qwen)
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Pipeline complete (should stop Qwen)")
    logger.info("="*80)

    complete_event = StageTransitionEvent(
        from_stage=PipelineStage.MERGE,
        to_stage=PipelineStage.COMPLETE,
        timestamp=asyncio.get_event_loop().time()
    )

    try:
        await coordinator.on_pipeline_complete(complete_event)
        logger.info("✓ Pipeline complete succeeded")
    except Exception as e:
        logger.error(f"✗ Pipeline complete failed: {e}", exc_info=True)
        return

    # Check final container states
    states = coordinator.get_container_states()
    logger.info(f"Final container states: {states}")

    logger.info("\n" + "="*80)
    logger.info("ALL TESTS COMPLETED")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
