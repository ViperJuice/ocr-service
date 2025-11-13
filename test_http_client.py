"""
Test HTTP Client Manager with Running Containers

Quick test to verify HTTP client infrastructure works correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.http_client_manager import HTTPClientManager, ModelType


async def test_http_client():
    """Test HTTP client manager with running containers"""

    print("="*60)
    print("Testing HTTP Client Manager")
    print("="*60)

    # Create client manager
    manager = HTTPClientManager()

    try:
        # Initialize (will check health automatically)
        print("\n1. Initializing HTTP clients...")
        await manager.initialize()
        print("   ✓ Clients initialized\n")

        # Get model info
        print("2. Fetching model information...")
        for model_type in ModelType:
            info = await manager.get_model_info(model_type)
            print(f"\n   {model_type.value}:")
            print(f"     Model: {info['model']}")
            print(f"     Transformers: {info['transformers_version']}")
            print(f"     Device: {info['device']}")
            print(f"     Dtype: {info['dtype']}")

        # Test health check
        print("\n3. Running health checks...")
        health_results = await manager.check_all_health()
        for model_type, health in health_results.items():
            status = "✓" if health.get("status") == "ready" else "✗"
            print(f"   {status} {model_type.value}: {health.get('status', 'unknown')}")

        print("\n" + "="*60)
        print("✓ All tests passed!")
        print("="*60)

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        raise

    finally:
        # Clean up
        await manager.close()


if __name__ == "__main__":
    asyncio.run(test_http_client())
