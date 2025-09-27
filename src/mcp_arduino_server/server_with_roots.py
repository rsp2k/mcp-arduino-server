"""
Arduino Server with MCP Roots support using FastMCP

This server uses client-provided roots for organizing sketches.
"""

import logging
from pathlib import Path
from typing import Optional
import os

from fastmcp import FastMCP, Context
from .config_with_roots import ArduinoServerConfigWithRoots
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


def create_roots_aware_server(base_config: Optional[ArduinoServerConfigWithRoots] = None) -> FastMCP:
    """
    Create an Arduino MCP server that uses client-provided roots for file organization.
    """
    if base_config is None:
        base_config = ArduinoServerConfigWithRoots()

    # Get package version for display
    try:
        from importlib.metadata import version
        package_version = version("mcp-arduino-server")
    except:
        package_version = "2025.09.26"

    # Create the FastMCP server instance
    mcp = FastMCP(
        name="Arduino Development Server (Roots-Aware)"
    )

    # This will hold our configuration after roots are known
    runtime_config = base_config

    # Add initialization hook to configure with roots
    @mcp.tool(name="arduino_initialize_with_roots")
    async def initialize_with_roots(ctx: Context) -> dict:
        """
        Initialize Arduino server with client-provided roots.
        This should be called once when the client connects.
        """
        nonlocal runtime_config

        try:
            # Get roots from context
            roots = await ctx.list_roots()
            logger.info(f"Received {len(roots) if roots else 0} roots from client")

            # Select appropriate directory based on roots
            sketch_dir = runtime_config.select_sketch_directory(roots)

            # Ensure directories exist
            runtime_config.ensure_directories()

            return {
                "success": True,
                "sketch_directory": str(sketch_dir),
                "roots_info": runtime_config.get_roots_info(),
                "message": f"Arduino server initialized with sketch directory: {sketch_dir}"
            }

        except Exception as e:
            logger.error(f"Failed to initialize with roots: {e}")
            # Fallback to default
            runtime_config.ensure_directories()
            return {
                "success": False,
                "sketch_directory": str(runtime_config.default_sketches_dir),
                "error": str(e),
                "message": f"Using default directory: {runtime_config.default_sketches_dir}"
            }

    # Tool to get current configuration
    @mcp.tool(name="arduino_get_active_directories")
    async def get_active_directories(ctx: Context) -> dict:
        """Get the currently active directories being used by the server"""
        return {
            "sketch_directory": str(runtime_config.sketches_base_dir),
            "build_directory": str(runtime_config.build_temp_dir),
            "arduino_data": str(runtime_config.arduino_data_dir),
            "arduino_user": str(runtime_config.arduino_user_dir),
            "roots_configured": runtime_config._active_roots is not None,
            "roots_info": runtime_config.get_roots_info()
        }

    # Enhanced sketch creation that respects roots
    @mcp.tool(name="arduino_create_sketch_in_root")
    async def create_sketch_in_root(
        ctx: Context,
        sketch_name: str,
        root_name: Optional[str] = None
    ) -> dict:
        """
        Create a sketch in a specific root or the selected directory.

        Args:
            sketch_name: Name of the sketch to create
            root_name: Optional specific root to use (if multiple roots available)
        """
        # If specific root requested, try to use it
        if root_name and runtime_config._active_roots:
            for root in runtime_config._active_roots:
                if root.get('name', '').lower() == root_name.lower():
                    root_path = Path(root['uri'].replace('file://', ''))
                    sketch_dir = root_path / 'Arduino_Sketches'
                    sketch_dir.mkdir(parents=True, exist_ok=True)

                    # Create sketch in this specific root
                    sketch_path = sketch_dir / sketch_name
                    sketch_path.mkdir(parents=True, exist_ok=True)

                    # Create .ino file
                    ino_file = sketch_path / f"{sketch_name}.ino"
                    ino_file.write_text(f"""
void setup() {{
  // Initialize serial communication
  Serial.begin(115200);
  Serial.println("{sketch_name} initialized");
}}

void loop() {{
  // Main code here
}}
""")

                    return {
                        "success": True,
                        "path": str(sketch_path),
                        "root": root_name,
                        "message": f"Created sketch in root '{root_name}': {sketch_path}"
                    }

        # Use default selected directory
        sketch_path = runtime_config.sketches_base_dir / sketch_name
        sketch_path.mkdir(parents=True, exist_ok=True)

        # Create .ino file
        ino_file = sketch_path / f"{sketch_name}.ino"
        ino_file.write_text(f"""
void setup() {{
  // Initialize serial communication
  Serial.begin(115200);
  Serial.println("{sketch_name} initialized");
}}

void loop() {{
  // Main code here
}}
""")

        return {
            "success": True,
            "path": str(sketch_path),
            "root": "default",
            "message": f"Created sketch in default location: {sketch_path}"
        }

    # Initialize all components with the runtime config
    sketch = ArduinoSketch(runtime_config)
    library = ArduinoLibrary(runtime_config)
    board = ArduinoBoard(runtime_config)
    debug = ArduinoDebug(runtime_config)
    wireviz = WireViz(runtime_config)
    serial = ArduinoSerial(runtime_config)

    # Initialize advanced components
    library_advanced = ArduinoLibrariesAdvanced(runtime_config)
    board_advanced = ArduinoBoardsAdvanced(runtime_config)
    compile_advanced = ArduinoCompileAdvanced(runtime_config)
    system_advanced = ArduinoSystemAdvanced(runtime_config)

    # Register all components
    sketch.register_all(mcp)
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

    # Add server info resource that includes roots information
    @mcp.resource(uri="server://info")
    async def get_server_info() -> str:
        """Get information about the server configuration including roots"""
        roots_status = "Configured" if runtime_config._active_roots else "Not configured (using defaults)"

        return f"""
# Arduino Development Server v{package_version}
## Roots-Aware Edition

## MCP Roots:
{runtime_config.get_roots_info()}

## Configuration:
- Arduino CLI: {runtime_config.arduino_cli_path}
- Active Sketch Directory: {runtime_config.sketches_base_dir}
- Roots Status: {roots_status}
- WireViz: {runtime_config.wireviz_path}
- Client Sampling: {'Enabled' if runtime_config.enable_client_sampling else 'Disabled'}

## Components:
- **Sketch Management**: Create, compile, upload Arduino sketches (roots-aware)
- **Library Management**: Search, install, manage Arduino libraries
- **Board Management**: Detect boards, install cores
- **Debug Support**: GDB-like debugging with breakpoints and variable inspection
- **Circuit Diagrams**: Generate WireViz diagrams from YAML or natural language
- **Serial Monitoring**: Memory-safe serial monitoring with circular buffer
- **Advanced Tools**: 35+ new tools for professional Arduino development

## Usage:
1. Call 'arduino_initialize_with_roots' to configure with client roots
2. Use 'arduino_get_active_directories' to see current configuration
3. All sketch operations will use the configured root directories
"""

    # Add a resource showing roots configuration
    @mcp.resource(uri="arduino://roots")
    async def get_roots_config() -> str:
        """Get current roots configuration"""
        return runtime_config.get_roots_info()

    logger.info("Arduino Development Server (Roots-Aware) initialized")
    logger.info("Call 'arduino_initialize_with_roots' to configure with client roots")

    return mcp


# Main entry point
def main():
    """Main entry point for roots-aware server"""
    # Check for environment variable to enable roots support
    use_roots = os.getenv("ARDUINO_USE_MCP_ROOTS", "true").lower() == "true"
    preferred_root = os.getenv("ARDUINO_PREFERRED_ROOT")

    if use_roots:
        config = ArduinoServerConfigWithRoots(
            preferred_root_name=preferred_root
        )
        server = create_roots_aware_server(config)
        logger.info("Starting Arduino server with MCP roots support")
    else:
        # Fall back to standard server if roots disabled
        from .server_refactored import create_server
        from .config import ArduinoServerConfig
        config = ArduinoServerConfig()
        server = create_server(config)
        logger.info("Starting Arduino server without roots support")

    server.run()


if __name__ == "__main__":
    main()