"""
Refactored Arduino Server using FastMCP component pattern

This is the main server that composes all components together.
Now with automatic MCP roots detection!
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
log = logging.getLogger(__name__)


class RootsAwareConfig:
    """Wrapper that enhances config with MCP roots support"""

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
                log.info(f"Found {len(self._roots)} MCP roots from client")

                # Select best root for Arduino sketches
                selected_path = self._select_best_root()
                if selected_path:
                    self._selected_root_path = selected_path
                    log.info(f"Using MCP root for sketches: {selected_path}")
                    self._initialized = True
                    return True
            else:
                log.info("No MCP roots provided by client, using environment/default config")

        except Exception as e:
            log.debug(f"Could not get MCP roots (client may not support them): {e}")

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
            info.append("MCP Roots: Not available or not yet initialized")

        info.append(f"Active Sketch Dir: {self.sketches_base_dir}")

        # Show source of directory
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


def create_server(config: Optional[ArduinoServerConfig] = None) -> FastMCP:
    """
    Factory function to create a properly configured Arduino MCP server
    using the component pattern with automatic MCP roots detection.
    """
    if config is None:
        config = ArduinoServerConfig()

    # Wrap config with roots awareness
    roots_config = RootsAwareConfig(config)

    # Ensure directories exist (will be updated when roots are detected)
    roots_config.ensure_directories()

    # Get package version for display
    try:
        from importlib.metadata import version
        package_version = version("mcp-arduino-server")
    except:
        package_version = "2025.09.26"

    # Create the FastMCP server instance
    mcp = FastMCP(
        name="Arduino Development Server"
    )

    # Track whether roots have been initialized
    roots_initialized = False

    async def ensure_roots_initialized(ctx: Context):
        """Ensure roots are initialized on first tool call"""
        nonlocal roots_initialized
        if not roots_initialized:
            await roots_config.initialize_with_context(ctx)
            roots_config.ensure_directories()
            roots_initialized = True
            log.info(f"Initialized with sketch directory: {roots_config.sketches_base_dir}")

    # Initialize all components with roots-aware config
    sketch = ArduinoSketch(roots_config)
    library = ArduinoLibrary(roots_config)
    board = ArduinoBoard(roots_config)
    debug = ArduinoDebug(roots_config)
    wireviz = WireViz(roots_config)
    serial = ArduinoSerial(roots_config)

    # Initialize advanced components
    library_advanced = ArduinoLibrariesAdvanced(roots_config)
    board_advanced = ArduinoBoardsAdvanced(roots_config)
    compile_advanced = ArduinoCompileAdvanced(roots_config)
    system_advanced = ArduinoSystemAdvanced(roots_config)

    # Register all components with appropriate prefixes
    sketch.register_all(mcp)    # No prefix - these are core functions
    library.register_all(mcp)   # No prefix - these are core functions
    board.register_all(mcp)     # No prefix - these are core functions
    debug.register_all(mcp)     # No prefix - these are debugging functions
    wireviz.register_all(mcp)   # No prefix - these are specialized
    serial.register_all(mcp)    # No prefix - serial monitoring functions

    # Register advanced components
    library_advanced.register_all(mcp)  # Advanced library management
    board_advanced.register_all(mcp)    # Advanced board management
    compile_advanced.register_all(mcp)  # Advanced compilation
    system_advanced.register_all(mcp)   # System management

    # Add tool to show current directory configuration
    @mcp.tool(name="arduino_show_directories")
    async def show_directories(ctx: Context) -> Dict[str, Any]:
        """Show current directory configuration including MCP roots status"""
        await ensure_roots_initialized(ctx)

        return {
            "sketch_directory": str(roots_config.sketches_base_dir),
            "build_directory": str(roots_config.build_temp_dir),
            "arduino_data": str(roots_config.arduino_data_dir),
            "arduino_user": str(roots_config.arduino_user_dir),
            "roots_info": roots_config.get_roots_info(),
            "env_vars": {
                "MCP_SKETCH_DIR": os.getenv("MCP_SKETCH_DIR", "not set"),
                "ARDUINO_CLI_PATH": os.getenv("ARDUINO_CLI_PATH", "not set"),
                "ARDUINO_SERIAL_BUFFER_SIZE": os.getenv("ARDUINO_SERIAL_BUFFER_SIZE", "10000"),
            }
        }

    # Add server info resource
    @mcp.resource(uri="server://info")
    async def get_server_info() -> str:
        """Get information about the server configuration"""
        roots_status = "Will be auto-detected on first tool use"
        if roots_initialized:
            roots_status = roots_config.get_roots_info()

        return f"""
# Arduino Development Server v{package_version}
## With Automatic MCP Roots Detection

## Directory Configuration:
{roots_status}

## Environment Variables:
- MCP_SKETCH_DIR: {os.getenv('MCP_SKETCH_DIR', 'not set')}
- ARDUINO_CLI_PATH: {roots_config.arduino_cli_path}
- ARDUINO_SERIAL_BUFFER_SIZE: {os.getenv('ARDUINO_SERIAL_BUFFER_SIZE', '10000')}

## Features:
- ✅ **Automatic MCP Roots Detection**: Uses client-provided project directories
- ✅ **Environment Variable Support**: MCP_SKETCH_DIR overrides roots
- ✅ **Smart Directory Selection**: Prefers 'arduino' named roots
- ✅ **No API keys required**: Uses client LLM sampling
- ✅ **60+ Professional Tools**: Complete Arduino toolkit
- ✅ **Memory-Safe Serial**: Circular buffer architecture
- ✅ **Full Arduino CLI Integration**: All features accessible

## How Directory Selection Works:
1. MCP client roots (automatic detection on first use)
2. MCP_SKETCH_DIR environment variable (override)
3. Default: ~/Documents/Arduino_MCP_Sketches

## Components:
- **Sketch Management**: Create, compile, upload Arduino sketches (roots-aware)
- **Library Management**: Search, install, manage Arduino libraries
- **Board Management**: Detect boards, install cores
- **Debug Support**: GDB-like debugging with breakpoints and variable inspection
- **Circuit Diagrams**: Generate WireViz diagrams from YAML or natural language
- **Serial Monitor**: Real-time serial communication with circular buffer

## Available Tool Categories:

### Sketch Tools:
- arduino_create_sketch: Create new sketch with boilerplate
- arduino_list_sketches: List all sketches
- arduino_compile_sketch: Compile without uploading
- arduino_upload_sketch: Compile and upload to board
- arduino_read_sketch: Read sketch file contents
- arduino_write_sketch: Write/update sketch files

### Library Tools:
- arduino_search_libraries: Search library index
- arduino_install_library: Install from index
- arduino_uninstall_library: Remove library
- arduino_list_library_examples: List library examples

### Board Tools:
- arduino_list_boards: List connected boards
- arduino_search_boards: Search board definitions
- arduino_install_core: Install board support
- arduino_list_cores: List installed cores
- arduino_update_cores: Update all cores

### Debug Tools:
- arduino_debug_start: Start debug session with GDB
- arduino_debug_interactive: Interactive debugging with elicitation
- arduino_debug_break: Set breakpoints
- arduino_debug_run: Run/continue/step execution
- arduino_debug_print: Print variable values
- arduino_debug_backtrace: Show call stack
- arduino_debug_watch: Monitor variable changes
- arduino_debug_memory: Examine memory contents
- arduino_debug_registers: Show CPU registers
- arduino_debug_stop: Stop debug session

### WireViz Tools:
- wireviz_generate_from_yaml: Create from YAML
- wireviz_generate_from_description: Create from description (AI)

### Serial Monitor Tools:
- serial_connect: Connect to serial port with auto-monitoring
- serial_disconnect: Disconnect from serial port
- serial_send: Send data/commands to serial port
- serial_read: Read data with cursor-based pagination
- serial_list_ports: List available serial ports
- serial_clear_buffer: Clear buffered serial data
- serial_reset_board: Reset Arduino board (DTR/RTS/1200bps)
- serial_monitor_state: Get current monitor state

## Resources:
- arduino://sketches: List of sketches
- arduino://libraries: Installed libraries
- arduino://boards: Connected boards
- arduino://debug/sessions: Active debug sessions
- wireviz://instructions: WireViz guide
- server://info: This information
"""

    # Log startup info
    log.info(f"🚀 Arduino Development Server v{package_version} initialized")
    log.info(f"📁 Sketch directory: {config.sketches_base_dir}")
    log.info(f"🔧 Arduino CLI: {config.arduino_cli_path}")
    log.info(f"📚 Components loaded: Sketch, Library, Board, Debug, WireViz, Serial Monitor")
    log.info(f"📡 Serial monitoring: Enabled with cursor-based streaming")
    log.info(f"🤖 Client sampling: {'Enabled' if roots_config.enable_client_sampling else 'Disabled'}")
    log.info("📁 MCP Roots: Will be auto-detected on first tool use")

    # Add resource for roots configuration
    @mcp.resource(uri="arduino://roots")
    async def get_roots_configuration() -> str:
        """Get current MCP roots configuration"""
        return roots_config.get_roots_info()

    return mcp


def main():
    """Main entry point for the server with MCP roots support"""
    config = ArduinoServerConfig()

    # Override from environment if set
    if env_sketch_dir := os.getenv("MCP_SKETCH_DIR"):
        config.sketches_base_dir = Path(env_sketch_dir).expanduser()
        log.info(f"Using MCP_SKETCH_DIR: {config.sketches_base_dir}")

    if env_cli_path := os.getenv("ARDUINO_CLI_PATH"):
        config.arduino_cli_path = env_cli_path
        log.info(f"Using ARDUINO_CLI_PATH: {config.arduino_cli_path}")

    # Create and run the server with automatic roots detection
    mcp = create_server(config)

    try:
        # Run the server using stdio transport
        mcp.run(transport='stdio')
    except KeyboardInterrupt:
        log.info("Server stopped by user")
    except Exception as e:
        log.exception(f"Server error: {e}")
        raise


if __name__ == "__main__":
    main()