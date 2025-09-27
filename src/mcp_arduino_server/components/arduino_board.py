"""Arduino Board management component"""
import asyncio
import json
import logging
import subprocess
from typing import List, Dict, Any, Optional

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool, mcp_resource
from mcp.types import ToolAnnotations

log = logging.getLogger(__name__)


class ArduinoBoard(MCPMixin):
    """Arduino board discovery and management component"""

    def __init__(self, config):
        """Initialize Arduino board component with configuration"""
        self.config = config
        self.arduino_cli_path = config.arduino_cli_path

    @mcp_resource(uri="arduino://boards")
    async def list_connected_boards(self) -> str:
        """List all connected Arduino boards as a resource"""
        boards = await self.list_boards()
        return boards

    @mcp_tool(
        name="arduino_list_boards",
        description="List all connected Arduino boards with details",
        annotations=ToolAnnotations(
            title="List Connected Boards",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def list_boards(
        self,
        ctx: Context | None = None
    ) -> str:
        """List all connected Arduino boards"""

        try:
            cmd = [
                self.arduino_cli_path,
                "board", "list",
                "--format", "json"
            ]

            log.info("Listing connected boards")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode != 0:
                return f"Error listing boards: {result.stderr}"

            # Parse JSON response
            try:
                data = json.loads(result.stdout)
                detected_ports = data.get('detected_ports', [])
            except json.JSONDecodeError:
                return "Failed to parse board list"

            if not detected_ports:
                return """No Arduino boards detected.

Common troubleshooting steps:
1. Check USB cable connection
2. Install board drivers if needed
3. Check permissions on serial port (may need to add user to dialout group on Linux)
4. Try a different USB port
"""

            # Format output
            output = f"Found {len(detected_ports)} connected board(s):\n\n"

            for port_info in detected_ports:
                port = port_info.get('port', {})
                boards = port_info.get('matching_boards', [])

                output += f"🔌 Port: {port.get('address', 'Unknown')}\n"
                output += f"   Protocol: {port.get('protocol', 'Unknown')}\n"
                output += f"   Label: {port.get('label', 'Unknown')}\n"

                if boards:
                    for board in boards:
                        output += f"   📋 Board: {board.get('name', 'Unknown')}\n"
                        output += f"      FQBN: {board.get('fqbn', 'Unknown')}\n"
                else:
                    output += "   ⚠️  No matching board found (may need to install core)\n"

                # Hardware info if available
                hw_info = port.get('hardware_id', '')
                if hw_info:
                    output += f"   Hardware ID: {hw_info}\n"

                output += "\n"

            return output

        except subprocess.TimeoutExpired:
            return f"Board detection timed out after {self.config.command_timeout} seconds"
        except Exception as e:
            log.exception(f"Failed to list boards: {e}")
            return f"Error: {str(e)}"

    @mcp_tool(
        name="arduino_search_boards",
        description="Search for Arduino board definitions in the index",
        annotations=ToolAnnotations(
            title="Search Board Definitions",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def search_boards(
        self,
        ctx: Context | None,
        query: str
    ) -> Dict[str, Any]:
        """Search for Arduino board definitions"""

        try:
            cmd = [
                self.arduino_cli_path,
                "board", "search",
                query,
                "--format", "json"
            ]

            log.info(f"Searching for boards: {query}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode != 0:
                return {
                    "error": "Board search failed",
                    "stderr": result.stderr
                }

            # Parse JSON response
            try:
                data = json.loads(result.stdout)
                boards = data.get('boards', [])
            except json.JSONDecodeError:
                return {"error": "Failed to parse board search results"}

            if not boards:
                return {
                    "message": f"No board definitions found for '{query}'",
                    "count": 0,
                    "boards": []
                }

            # Format results
            formatted_boards = []
            for board in boards:
                formatted_boards.append({
                    "name": board.get('name', 'Unknown'),
                    "fqbn": board.get('fqbn', ''),
                    "platform": board.get('platform', {}).get('id', ''),
                    "package": board.get('platform', {}).get('maintainer', ''),
                })

            return {
                "success": True,
                "query": query,
                "count": len(formatted_boards),
                "boards": formatted_boards,
                "hint": "To use a board, install its core with 'arduino_install_core'"
            }

        except subprocess.TimeoutExpired:
            return {"error": f"Search timed out after {self.config.command_timeout} seconds"}
        except Exception as e:
            log.exception(f"Board search failed: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_install_core",
        description="Install an Arduino board core (platform)",
        annotations=ToolAnnotations(
            title="Install Board Core",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def install_core(
        self,
        ctx: Context | None,
        core_spec: str
    ) -> Dict[str, Any]:
        """Install an Arduino board core/platform

        Args:
            core_spec: Core specification (e.g., 'arduino:avr', 'esp32:esp32')
        """

        try:
            if ctx:
                await ctx.info(f"🔧 Starting installation of core: {core_spec}")
                await ctx.report_progress(5, 100)

            cmd = [
                self.arduino_cli_path,
                "core", "install",
                core_spec
            ]

            log.info(f"Installing core: {core_spec}")

            if ctx:
                await ctx.debug(f"Executing: {' '.join(cmd)}")
                await ctx.report_progress(10, 100)

            # Run with async subprocess for progress tracking
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Track progress through output
            stdout_data = []
            stderr_data = []
            progress_val = 15
            downloading_count = 0

            async def read_stream(stream, data_list):
                nonlocal progress_val, downloading_count
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode().strip()
                    data_list.append(decoded)

                    # Parse output for progress indicators
                    if ctx and decoded:
                        if "downloading" in decoded.lower():
                            downloading_count += 1
                            # Cores often have multiple downloads (toolchain, core, tools)
                            progress_val = min(20 + (downloading_count * 15), 70)
                            await ctx.report_progress(progress_val, 100)
                            await ctx.info(f"📦 {decoded}")
                        elif "installing" in decoded.lower():
                            progress_val = min(progress_val + 10, 85)
                            await ctx.report_progress(progress_val, 100)
                            await ctx.debug(f"Installing: {decoded}")
                        elif "installed" in decoded.lower() or "completed" in decoded.lower():
                            progress_val = min(progress_val + 5, 95)
                            await ctx.report_progress(progress_val, 100)
                        elif "platform" in decoded.lower():
                            if ctx:
                                await ctx.debug(decoded)

            # Read both streams
            await asyncio.gather(
                read_stream(process.stdout, stdout_data),
                read_stream(process.stderr, stderr_data)
            )

            await process.wait()

            stdout = '\n'.join(stdout_data)
            stderr = '\n'.join(stderr_data)

            if process.returncode == 0:
                if ctx:
                    await ctx.report_progress(100, 100)
                    await ctx.info(f"✅ Core '{core_spec}' installed successfully")
                return {
                    "success": True,
                    "message": f"Core '{core_spec}' installed successfully",
                    "output": stdout
                }
            else:
                # Check if already installed
                if "already installed" in stderr.lower():
                    if ctx:
                        await ctx.report_progress(100, 100)
                        await ctx.info(f"Core '{core_spec}' is already installed")
                    return {
                        "success": True,
                        "message": f"Core '{core_spec}' is already installed",
                        "output": stderr
                    }
                if ctx:
                    await ctx.error(f"❌ Core installation failed for '{core_spec}'")
                    await ctx.debug(f"Error details: {stderr}")
                return {
                    "error": "Core installation failed",
                    "core": core_spec,
                    "stderr": stderr,
                    "hint": "Make sure the core spec is correct (e.g., 'arduino:avr')"
                }

        except asyncio.TimeoutError:
            if ctx:
                await ctx.error(f"Installation timed out after {self.config.command_timeout * 3} seconds")
            return {"error": f"Installation timed out after {self.config.command_timeout * 3} seconds"}
        except Exception as e:
            log.exception(f"Core installation failed: {e}")
            if ctx:
                await ctx.error(f"Installation error: {str(e)}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_list_cores",
        description="List all installed Arduino board cores",
        annotations=ToolAnnotations(
            title="List Installed Cores",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def list_cores(
        self,
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """List all installed Arduino board cores"""

        try:
            cmd = [
                self.arduino_cli_path,
                "core", "list",
                "--format", "json"
            ]

            log.info("Listing installed cores")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode != 0:
                return {
                    "error": "Failed to list cores",
                    "stderr": result.stderr
                }

            # Parse JSON response
            try:
                data = json.loads(result.stdout)
                platforms = data.get('platforms', [])
            except json.JSONDecodeError:
                return {"error": "Failed to parse core list"}

            if not platforms:
                return {
                    "message": "No cores installed. Install with 'arduino_install_core'",
                    "count": 0,
                    "cores": [],
                    "hint": "Try 'arduino_install_core arduino:avr' for basic Arduino support"
                }

            # Format results
            formatted_cores = []
            for platform in platforms:
                formatted_cores.append({
                    "id": platform.get('id', 'Unknown'),
                    "installed": platform.get('installed', 'Unknown'),
                    "latest": platform.get('latest', 'Unknown'),
                    "name": platform.get('name', 'Unknown'),
                    "maintainer": platform.get('maintainer', 'Unknown'),
                    "website": platform.get('website', ''),
                    "boards": [b.get('name', '') for b in platform.get('boards', [])]
                })

            return {
                "success": True,
                "count": len(formatted_cores),
                "cores": formatted_cores
            }

        except subprocess.TimeoutExpired:
            return {"error": f"List operation timed out after {self.config.command_timeout} seconds"}
        except Exception as e:
            log.exception(f"Failed to list cores: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_install_esp32",
        description="Install ESP32 board support with proper board package URL",
        annotations=ToolAnnotations(
            title="Install ESP32 Support",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def install_esp32(
        self,
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Install ESP32 board support with automatic board package URL configuration"""

        try:
            esp32_url = "https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json"

            if ctx:
                await ctx.info("🔧 Installing ESP32 board support...")
                await ctx.report_progress(5, 100)

            # First, update the index with ESP32 board package URL
            update_cmd = [
                self.arduino_cli_path,
                "core", "update-index",
                "--additional-urls", esp32_url
            ]

            log.info("Updating board index with ESP32 URL")

            if ctx:
                await ctx.debug(f"Adding ESP32 board package URL: {esp32_url}")
                await ctx.report_progress(10, 100)

            # Run index update asynchronously
            process = await asyncio.create_subprocess_exec(
                *update_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=60  # 60 seconds for index update
            )

            if process.returncode != 0:
                if ctx:
                    await ctx.error("Failed to update board index")
                return {
                    "error": "Failed to update board index with ESP32 URL",
                    "stderr": stderr_data.decode()
                }

            if ctx:
                await ctx.info("✅ Board index updated with ESP32 support")
                await ctx.report_progress(20, 100)

            # Now install the ESP32 core
            install_cmd = [
                self.arduino_cli_path,
                "core", "install", "esp32:esp32",
                "--additional-urls", esp32_url
            ]

            log.info("Installing ESP32 core")

            if ctx:
                await ctx.info("📦 Downloading ESP32 core packages...")
                await ctx.info("ℹ️  This may take several minutes (>500MB of downloads)")
                await ctx.report_progress(25, 100)

            # Run installation with longer timeout for large downloads
            process = await asyncio.create_subprocess_exec(
                *install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_lines = []
            stderr_lines = []
            progress_val = 30

            # Read output line by line for progress tracking
            async def read_stream(stream, lines_list, is_stderr=False):
                nonlocal progress_val
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode().strip()
                    lines_list.append(decoded)

                    if ctx and decoded:
                        # Track progress based on output
                        if "downloading" in decoded.lower():
                            # Extract package name if possible
                            if "esp32:" in decoded:
                                package_name = decoded.split("esp32:")[-1].split()[0]
                                await ctx.info(f"📦 Downloading: esp32:{package_name}")
                            else:
                                await ctx.debug(f"📦 {decoded}")
                            progress_val = min(progress_val + 5, 80)
                            await ctx.report_progress(progress_val, 100)
                        elif "installing" in decoded.lower():
                            await ctx.debug(f"⚙️  {decoded}")
                            progress_val = min(progress_val + 3, 90)
                            await ctx.report_progress(progress_val, 100)
                        elif "installed" in decoded.lower():
                            await ctx.info(f"✅ {decoded}")
                            progress_val = min(progress_val + 2, 95)
                            await ctx.report_progress(progress_val, 100)

            # Read both streams concurrently
            await asyncio.gather(
                read_stream(process.stdout, stdout_lines),
                read_stream(process.stderr, stderr_lines, True)
            )

            # Wait for process completion with extended timeout
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=1800  # 30 minutes for large ESP32 downloads
                )
            except asyncio.TimeoutError:
                process.kill()
                if ctx:
                    await ctx.error("❌ ESP32 installation timed out after 30 minutes")
                return {
                    "error": "ESP32 installation timed out",
                    "hint": "Try running 'arduino-cli core install esp32:esp32' manually"
                }

            stdout_text = '\n'.join(stdout_lines)
            stderr_text = '\n'.join(stderr_lines)

            if process.returncode == 0:
                if ctx:
                    await ctx.report_progress(100, 100)
                    await ctx.info("🎉 ESP32 core installed successfully!")
                    await ctx.info("You can now use ESP32 boards with Arduino")

                # List installed ESP32 boards
                list_cmd = [
                    self.arduino_cli_path,
                    "board", "listall", "esp32"
                ]

                list_result = subprocess.run(
                    list_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                return {
                    "success": True,
                    "message": "ESP32 core installed successfully",
                    "available_boards": list_result.stdout if list_result.returncode == 0 else "Run 'arduino_list_boards' to see available ESP32 boards",
                    "next_steps": [
                        "Connect your ESP32 board via USB",
                        "Run 'arduino_list_boards' to detect it",
                        "Use the detected FQBN for compilation"
                    ]
                }
            else:
                # Check if already installed
                if "already installed" in stderr_text.lower():
                    if ctx:
                        await ctx.report_progress(100, 100)
                        await ctx.info("ESP32 core is already installed")
                    return {
                        "success": True,
                        "message": "ESP32 core is already installed",
                        "hint": "Run 'arduino_list_boards' to detect connected ESP32 boards"
                    }

                if ctx:
                    await ctx.error("❌ ESP32 installation failed")
                    await ctx.debug(f"Error: {stderr_text}")

                return {
                    "error": "ESP32 installation failed",
                    "stderr": stderr_text,
                    "hint": "Check your internet connection and try again"
                }

        except Exception as e:
            log.exception(f"ESP32 installation failed: {e}")
            if ctx:
                await ctx.error(f"Installation error: {str(e)}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_update_cores",
        description="Update all installed Arduino cores to latest versions",
        annotations=ToolAnnotations(
            title="Update All Cores",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def update_cores(
        self,
        ctx: Context | None = None
    ) -> Dict[str, Any]:
        """Update all installed Arduino cores"""

        try:
            cmd = [
                self.arduino_cli_path,
                "core", "update-index"
            ]

            log.info("Updating core index")

            # First update the index
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode != 0:
                return {
                    "error": "Failed to update core index",
                    "stderr": result.stderr
                }

            # Now upgrade all cores
            cmd = [
                self.arduino_cli_path,
                "core", "upgrade"
            ]

            log.info("Upgrading all cores")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout * 3  # Updates can be slow
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "All cores updated successfully",
                    "output": result.stdout
                }
            else:
                if "already up to date" in result.stderr.lower():
                    return {
                        "success": True,
                        "message": "All cores are already up to date",
                        "output": result.stderr
                    }
                return {
                    "error": "Core update failed",
                    "stderr": result.stderr
                }

        except subprocess.TimeoutExpired:
            return {"error": f"Update timed out after {self.config.command_timeout * 3} seconds"}
        except Exception as e:
            log.exception(f"Core update failed: {e}")
            return {"error": str(e)}