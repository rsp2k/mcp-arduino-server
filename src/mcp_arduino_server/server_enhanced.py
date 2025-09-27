"""
Enhanced Arduino Server with automatic MCP Roots detection

Automatically uses client-provided roots when available, falls back to env vars.
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastmcp import FastMCP, Context
from .config import ArduinoServerConfig
from .components import (
    ArduinoBoard,
    ArduinoDebug,
    ArduinoLibrary,
    ArduinoSketch,
    WireViz,
)
from .components.arduino_serial import ArduinoSerial
from .components.arduino_libraries_advanced import ArduinoLibrariesAdvanced
from .components.arduino_boards_advanced import ArduinoBoardsAdvanced
from .components.arduino_compile_advanced import ArduinoCompileAdvanced
from .components.arduino_system_advanced import ArduinoSystemAdvanced

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RootsAwareConfig:
    """Wrapper that enhances config with roots support"""

    def __init__(self, base_config: ArduinoServerConfig):
        self.base_config = base_config
        self._roots: Optional[List[Dict[str, Any]]] = None
        self._selected_root_path: Optional[Path] = None
        self._initialized = False

    async def initialize_with_context(self, ctx: Context) -> bool:
        """Initialize with MCP context to get roots"""
        try:
            # Try to get roots from context
            self._roots = await ctx.list_roots()

            if self._roots:
                logger.info(f"Found {len(self._roots)} MCP roots")

                # Select best root for Arduino sketches
                selected_path = self._select_best_root()
                if selected_path:
                    self._selected_root_path = selected_path
                    logger.info(f"Using MCP root for sketches: {selected_path}")
                    self._initialized = True
                    return True
            else:
                logger.info("No MCP roots available, using environment/default config")

        except Exception as e:
            logger.debug(f"Could not get MCP roots (client may not support them): {e}")

        self._initialized = True
        return False

    def _select_best_root(self) -> Optional[Path]:
        """Select the best root for Arduino sketches"""
        if not self._roots:
            return None

        # Priority order for root selection
        for root in self._roots:
            try:
                root_name = root.get('name', '').lower()
                root_uri = root.get('uri', '')

                # Skip non-file URIs
                if not root_uri.startswith('file://'):
                    continue

                root_path = Path(root_uri.replace('file://', ''))

                # Priority 1: Root named 'arduino' or containing 'arduino'
                if 'arduino' in root_name:
                    logger.info(f"Selected Arduino-specific root: {root_name}")
                    return root_path / 'sketches'

                # Priority 2: Root named 'projects' or 'code'
                if any(term in root_name for term in ['project', 'code', 'dev']):
                    logger.info(f"Selected development root: {root_name}")
                    return root_path / 'Arduino_Sketches'

            except Exception as e:
                logger.warning(f"Error processing root {root}: {e}")
                continue

        # Use first available root as fallback
        if self._roots:
            first_root = self._roots[0]
            root_uri = first_root.get('uri', '')
            if root_uri.startswith('file://'):
                root_path = Path(root_uri.replace('file://', ''))
                logger.info(f"Using first available root: {first_root.get('name')}")
                return root_path / 'Arduino_Sketches'

        return None

    @property
    def sketches_base_dir(self) -> Path:
        """Get sketches directory (roots-aware)"""
        # Use MCP root if available and initialized
        if self._initialized and self._selected_root_path:
            return self._selected_root_path

        # Check environment variable override
        env_sketch_dir = os.getenv('MCP_SKETCH_DIR')
        if env_sketch_dir:
            return Path(env_sketch_dir).expanduser()

        # Fall back to base config default
        return self.base_config.sketches_base_dir

    @property
    def sketch_dir(self) -> Path:
        """Alias for compatibility"""
        return self.sketches_base_dir

    @property
    def build_temp_dir(self) -> Path:
        """Build temp directory"""
        return self.sketches_base_dir / "_build_temp"

    def ensure_directories(self) -> None:
        """Ensure all directories exist"""
        self.sketches_base_dir.mkdir(parents=True, exist_ok=True)
        self.build_temp_dir.mkdir(parents=True, exist_ok=True)
        self.base_config.arduino_data_dir.mkdir(parents=True, exist_ok=True)
        self.base_config.arduino_user_dir.mkdir(parents=True, exist_ok=True)

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

        # Show if using env var
        if os.getenv('MCP_SKETCH_DIR'):
            info.append(f"  (from MCP_SKETCH_DIR env var)")
        elif self._selected_root_path:
            info.append(f"  (from MCP root)")
        else:
            info.append(f"  (default)")

        return "\n".join(info)

    # Delegate all other attributes to base config
    def __getattr__(self, name):
        return getattr(self.base_config, name)


def create_enhanced_server(base_config: Optional[ArduinoServerConfig] = None) -> FastMCP:
    """
    Create Arduino server with automatic roots detection and env var support.
    """
    if base_config is None:
        base_config = ArduinoServerConfig()

    # Wrap config with roots awareness
    config = RootsAwareConfig(base_config)

    # Ensure base directories exist (may be overridden by roots later)
    config.ensure_directories()

    # Get package version
    try:
        from importlib.metadata import version
        package_version = version("mcp-arduino-server")
    except:
        package_version = "2025.09.27"

    # Create the FastMCP server
    mcp = FastMCP(
        name="Arduino Development Server"
    )

    # Hook to initialize with roots when first tool is called
    roots_initialized = False

    async def ensure_roots_initialized(ctx: Context):
        """Ensure roots are initialized before any operation"""
        nonlocal roots_initialized
        if not roots_initialized:
            await config.initialize_with_context(ctx)
            config.ensure_directories()
            roots_initialized = True
            logger.info(f"Initialized with sketch directory: {config.sketches_base_dir}")

    # Wrap original sketch component to add roots initialization
    original_sketch = ArduinoSketch(config)

    # Create wrapper for sketch creation that ensures roots
    original_create = original_sketch.create_sketch

    @mcp.tool(name="arduino_create_sketch")
    async def create_sketch(ctx: Context, sketch_name: str) -> Dict[str, Any]:
        """Create a new Arduino sketch (roots-aware)"""
        await ensure_roots_initialized(ctx)
        # Now config has been initialized with roots if available
        return await original_create(sketch_name=sketch_name, ctx=ctx)

    # Similarly wrap other sketch operations
    original_list = original_sketch.list_sketches

    @mcp.tool(name="arduino_list_sketches")
    async def list_sketches(ctx: Context) -> Dict[str, Any]:
        """List all Arduino sketches (roots-aware)"""
        await ensure_roots_initialized(ctx)
        return await original_list(ctx=ctx)

    # Initialize all components with wrapped config
    library = ArduinoLibrary(config)
    board = ArduinoBoard(config)
    debug = ArduinoDebug(config)
    wireviz = WireViz(config)
    serial = ArduinoSerial(config)

    # Initialize advanced components
    library_advanced = ArduinoLibrariesAdvanced(config)
    board_advanced = ArduinoBoardsAdvanced(config)
    compile_advanced = ArduinoCompileAdvanced(config)
    system_advanced = ArduinoSystemAdvanced(config)

    # Register components (sketch is partially registered above)
    # Register remaining sketch tools
    for tool_name, tool_func in original_sketch._get_tools():
        if tool_name not in ["arduino_create_sketch", "arduino_list_sketches"]:
            mcp.add_tool(tool_func)

    library.register_all(mcp)
    board.register_all(mcp)
    debug.register_all(mcp)
    wireviz.register_all(mcp)
    serial.register_all(mcp)

    # Register advanced components
    library_advanced.register_all(mcp)
    board_advanced.register_all(mcp)
    compile_advanced.register_all(mcp)
    system_advanced.register_all(mcp)

    # Add tool to show roots configuration
    @mcp.tool(name="arduino_show_directories")
    async def show_directories(ctx: Context) -> Dict[str, Any]:
        """Show current directory configuration including MCP roots status"""
        await ensure_roots_initialized(ctx)

        return {
            "sketch_directory": str(config.sketches_base_dir),
            "build_directory": str(config.build_temp_dir),
            "arduino_data": str(config.arduino_data_dir),
            "arduino_user": str(config.arduino_user_dir),
            "roots_info": config.get_roots_info(),
            "env_vars": {
                "MCP_SKETCH_DIR": os.getenv("MCP_SKETCH_DIR", "not set"),
                "ARDUINO_CLI_PATH": os.getenv("ARDUINO_CLI_PATH", "not set"),
            }
        }

    # Add server info resource
    @mcp.resource(uri="server://info")
    async def get_server_info() -> str:
        """Get server configuration info"""
        roots_status = "Will be detected on first use"
        if roots_initialized:
            roots_status = config.get_roots_info()

        return f"""
# Arduino Development Server v{package_version}
## With Automatic Roots Detection

## Directory Configuration:
{roots_status}

## Environment Variables:
- MCP_SKETCH_DIR: {os.getenv('MCP_SKETCH_DIR', 'not set')}
- ARDUINO_CLI_PATH: {config.arduino_cli_path}
- ARDUINO_SERIAL_BUFFER_SIZE: {os.getenv('ARDUINO_SERIAL_BUFFER_SIZE', '10000')}

## Features:
- **Automatic Roots Detection**: Uses client-provided roots when available
- **Environment Override**: MCP_SKETCH_DIR overrides roots
- **Fallback Support**: Uses defaults if no roots or env vars
- **60+ Tools**: Complete Arduino development toolkit
- **Memory-Safe Serial**: Circular buffer prevents crashes
- **Professional Debugging**: GDB integration with breakpoints

## How Directory Selection Works:
1. Check for MCP client roots (automatic)
2. Check MCP_SKETCH_DIR environment variable
3. Use default ~/Documents/Arduino_MCP_Sketches

Call 'arduino_show_directories' to see current configuration.
"""

    logger.info("Arduino Development Server initialized with automatic roots detection")
    return mcp


# Main entry point
def main():
    """Main entry point"""
    # Load config from environment
    config = ArduinoServerConfig()

    # Override from environment if set
    if env_sketch_dir := os.getenv("MCP_SKETCH_DIR"):
        config.sketches_base_dir = Path(env_sketch_dir).expanduser()

    if env_cli_path := os.getenv("ARDUINO_CLI_PATH"):
        config.arduino_cli_path = env_cli_path

    # Create enhanced server
    server = create_enhanced_server(config)

    logger.info("Starting Arduino server with automatic roots detection and env var support")
    server.run()


if __name__ == "__main__":
    main()