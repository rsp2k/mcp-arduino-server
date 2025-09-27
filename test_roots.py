#!/usr/bin/env python3
"""Test MCP roots functionality"""

import asyncio
import sys
from pathlib import Path

# Add source to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_arduino_server.config import ArduinoServerConfig
from mcp_arduino_server.server_refactored import RootsAwareConfig


async def test_roots_config():
    """Test the roots-aware configuration"""

    # Create base config
    base_config = ArduinoServerConfig()
    print(f"Base sketch dir: {base_config.sketches_base_dir}")

    # Create roots-aware wrapper
    roots_config = RootsAwareConfig(base_config)

    # Test without roots (should use default)
    print(f"\nWithout roots initialization:")
    print(f"  Sketch dir: {roots_config.sketches_base_dir}")
    print(f"  Is initialized: {roots_config._initialized}")

    # Simulate MCP roots
    class MockContext:
        async def list_roots(self):
            return [
                {
                    "name": "my-arduino-projects",
                    "uri": "file:///home/user/projects/arduino"
                },
                {
                    "name": "dev-workspace",
                    "uri": "file:///home/user/workspace"
                }
            ]

    # Test with roots
    mock_ctx = MockContext()
    await roots_config.initialize_with_context(mock_ctx)

    print(f"\nWith roots initialization:")
    print(f"  Sketch dir: {roots_config.sketches_base_dir}")
    print(f"  Is initialized: {roots_config._initialized}")
    print(f"\nRoots info:")
    print(roots_config.get_roots_info())

    # Test environment variable override
    import os
    os.environ["MCP_SKETCH_DIR"] = "/tmp/test_sketches"

    # Create new config to test env var
    roots_config2 = RootsAwareConfig(base_config)
    print(f"\nWith MCP_SKETCH_DIR env var:")
    print(f"  Sketch dir: {roots_config2.sketches_base_dir}")


if __name__ == "__main__":
    asyncio.run(test_roots_config())