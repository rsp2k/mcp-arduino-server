#!/usr/bin/env python3
"""Test MCP roots functionality without full imports"""

import asyncio
import sys
from pathlib import Path

# Add source to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import only what we need directly
import logging
import os
from typing import Optional, List, Dict, Any

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class ArduinoServerConfig:
    """Minimal config for testing"""
    def __init__(self):
        self.sketches_base_dir = Path.home() / "Documents" / "Arduino_MCP_Sketches"
        self.arduino_data_dir = Path.home() / ".arduino15"
        self.arduino_user_dir = Path.home() / "Documents" / "Arduino"


class RootsAwareConfig:
    """Copied from server_refactored.py for testing"""

    def __init__(self, base_config):
        self.base_config = base_config
        self._roots: Optional[List[Dict[str, Any]]] = None
        self._selected_root_path: Optional[Path] = None
        self._initialized = False

    async def initialize_with_context(self, ctx):
        """Initialize with MCP context to get roots"""
        try:
            # Try to get roots from context
            self._roots = await ctx.list_roots()

            if self._roots:
                log.info(f"Found {len(self._roots)} MCP roots from client")

                # Select best root for Arduino sketches
                selected_path = self._select_best_root()
                if selected_path:
                    self._selected_root_path = selected_path
                    log.info(f"Using MCP root for sketches: {selected_path}")
                    self._initialized = True
                    return True
            else:
                log.info("No MCP roots provided by client")

        except Exception as e:
            log.debug(f"Could not get MCP roots: {e}")

        self._initialized = True
        return False

    def _select_best_root(self) -> Optional[Path]:
        """Select the best root for Arduino sketches"""
        if not self._roots:
            return None

        for root in self._roots:
            try:
                root_name = root.get('name', '').lower()
                root_uri = root.get('uri', '')

                if not root_uri.startswith('file://'):
                    continue

                root_path = Path(root_uri.replace('file://', ''))

                # Priority 1: Root named 'arduino'
                if 'arduino' in root_name:
                    log.info(f"Selected Arduino-specific root: {root_name}")
                    return root_path / 'sketches'

                # Priority 2: Root named 'projects' or 'code'
                if any(term in root_name for term in ['project', 'code', 'dev']):
                    log.info(f"Selected development root: {root_name}")
                    return root_path / 'Arduino_Sketches'

            except Exception as e:
                log.warning(f"Error processing root {root}: {e}")
                continue

        # Use first available root as fallback
        if self._roots:
            first_root = self._roots[0]
            root_uri = first_root.get('uri', '')
            if root_uri.startswith('file://'):
                root_path = Path(root_uri.replace('file://', ''))
                log.info(f"Using first available root: {first_root.get('name')}")
                return root_path / 'Arduino_Sketches'

        return None

    @property
    def sketches_base_dir(self) -> Path:
        """Get sketches directory (roots-aware)"""
        if self._initialized and self._selected_root_path:
            return self._selected_root_path

        # Check environment variable override
        env_sketch_dir = os.getenv('MCP_SKETCH_DIR')
        if env_sketch_dir:
            return Path(env_sketch_dir).expanduser()

        # Fall back to base config default
        return self.base_config.sketches_base_dir

    def get_roots_info(self) -> str:
        """Get information about roots configuration"""
        info = []

        if self._roots:
            info.append(f"MCP Roots Available: {len(self._roots)}")
            for root in self._roots:
                name = root.get('name', 'unnamed')
                uri = root.get('uri', 'unknown')
                info.append(f"  - {name}: {uri}")
        else:
            info.append("MCP Roots: Not available")

        info.append(f"Active Sketch Dir: {self.sketches_base_dir}")

        if os.getenv('MCP_SKETCH_DIR'):
            info.append(f"  (from MCP_SKETCH_DIR env var)")
        elif self._selected_root_path:
            info.append(f"  (from MCP root)")
        else:
            info.append(f"  (default)")

        return "\n".join(info)


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
    os.environ["MCP_SKETCH_DIR"] = "/tmp/test_sketches"

    # Create new config to test env var
    roots_config2 = RootsAwareConfig(base_config)
    print(f"\nWith MCP_SKETCH_DIR env var:")
    print(f"  Sketch dir: {roots_config2.sketches_base_dir}")


if __name__ == "__main__":
    asyncio.run(test_roots_config())