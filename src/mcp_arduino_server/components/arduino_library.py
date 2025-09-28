"""Arduino Library management component"""
import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_resource, mcp_tool
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class LibrarySearchRequest(BaseModel):
    """Request model for library search"""
    query: str = Field(..., description="Search query for libraries")
    limit: int = Field(10, description="Maximum number of results", ge=1, le=100)


class ArduinoLibrary(MCPMixin):
    """Arduino library management component"""

    def __init__(self, config):
        """Initialize Arduino library component with configuration"""
        self.config = config
        self.arduino_cli_path = config.arduino_cli_path
        self.arduino_user_dir = config.arduino_user_dir

        # Try to import fuzzy search if available
        try:
            from thefuzz import fuzz
            self.fuzz = fuzz
            self.fuzzy_available = True
        except ImportError:
            self.fuzz = None
            self.fuzzy_available = False
            log.warning("thefuzz not available - fuzzy search disabled")

    @mcp_resource(uri="arduino://libraries")
    async def list_installed_libraries(self) -> str:
        """List all installed Arduino libraries"""
        libraries = await self._get_installed_libraries()
        if not libraries:
            return "No libraries installed. Use 'arduino_install_library' to install libraries."

        output = f"Installed Arduino Libraries ({len(libraries)}):\n\n"
        for lib in libraries:
            output += f"📚 {lib['name']} v{lib.get('version', 'unknown')}\n"
            if lib.get('author'):
                output += f"   Author: {lib['author']}\n"
            if lib.get('sentence'):
                output += f"   {lib['sentence']}\n"
            output += "\n"

        return output

    @mcp_tool(
        name="arduino_search_libraries",
        description="Search for Arduino libraries in the official index",
        annotations=ToolAnnotations(
            title="Search Arduino Libraries",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def search_libraries(
        self,
        ctx: Context | None,
        query: str,
        limit: int = 10
    ) -> dict[str, Any]:
        """Search for Arduino libraries online"""

        try:
            # Validate request
            request = LibrarySearchRequest(query=query, limit=limit)

            # Search using arduino-cli
            cmd = [
                self.arduino_cli_path,
                "lib", "search",
                request.query,
                "--format", "json"
            ]

            log.info(f"Searching libraries: {request.query}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode != 0:
                return {
                    "error": "Library search failed",
                    "stderr": result.stderr
                }

            # Parse JSON response
            try:
                data = json.loads(result.stdout)
                libraries = data.get('libraries', [])
            except json.JSONDecodeError:
                return {"error": "Failed to parse library search results"}

            # Limit results
            libraries = libraries[:request.limit]

            if not libraries:
                return {
                    "message": f"No libraries found for '{request.query}'",
                    "count": 0,
                    "libraries": []
                }

            # Format results
            formatted_libs = []
            for lib in libraries:
                formatted_libs.append({
                    "name": lib.get('name', 'Unknown'),
                    "author": lib.get('author', 'Unknown'),
                    "version": lib.get('latest', {}).get('version', 'Unknown'),
                    "sentence": lib.get('sentence', ''),
                    "paragraph": lib.get('paragraph', ''),
                    "category": lib.get('category', 'Uncategorized'),
                    "architectures": lib.get('architectures', [])
                })

            return {
                "success": True,
                "query": request.query,
                "count": len(formatted_libs),
                "libraries": formatted_libs
            }

        except subprocess.TimeoutExpired:
            return {"error": f"Search timed out after {self.config.command_timeout} seconds"}
        except Exception as e:
            log.exception(f"Library search failed: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_install_library",
        description="Install an Arduino library from the official index",
        annotations=ToolAnnotations(
            title="Install Arduino Library",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def install_library(
        self,
        ctx: Context | None,
        library_name: str,
        version: str | None = None
    ) -> dict[str, Any]:
        """Install an Arduino library"""

        try:
            # Send initial log and progress
            if ctx:
                await ctx.info(f"Starting installation of library: {library_name}")
                await ctx.report_progress(10, 100)

            # Build install command
            cmd = [
                self.arduino_cli_path,
                "lib", "install",
                library_name
            ]

            if version:
                cmd.append(f"@{version}")

            log.info(f"Installing library: {library_name}")

            # Report download starting
            if ctx:
                await ctx.report_progress(20, 100)
                await ctx.debug(f"Executing: {' '.join(cmd)}")

            # Run installation with async subprocess for progress updates
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Monitor process output for progress
            stdout_data = []
            stderr_data = []
            progress_val = 30

            async def read_stream(stream, data_list, is_stderr=False):
                nonlocal progress_val
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode().strip()
                    data_list.append(decoded)

                    # Update progress based on output
                    if ctx and decoded:
                        if "downloading" in decoded.lower():
                            progress_val = min(50, progress_val + 5)
                            await ctx.report_progress(progress_val, 100)
                            await ctx.debug(f"Download progress: {decoded}")
                        elif "installing" in decoded.lower():
                            progress_val = min(80, progress_val + 10)
                            await ctx.report_progress(progress_val, 100)
                            await ctx.info(f"Installing: {decoded}")
                        elif "installed" in decoded.lower():
                            progress_val = 90
                            await ctx.report_progress(progress_val, 100)

            # Read both streams concurrently
            await asyncio.gather(
                read_stream(process.stdout, stdout_data),
                read_stream(process.stderr, stderr_data, is_stderr=True)
            )

            # Wait for process to complete
            await process.wait()

            stdout = '\n'.join(stdout_data)
            stderr = '\n'.join(stderr_data)

            if process.returncode == 0:
                if ctx:
                    await ctx.report_progress(100, 100)
                    await ctx.info(f"✅ Library '{library_name}' installed successfully")
                return {
                    "success": True,
                    "message": f"Library '{library_name}' installed successfully",
                    "output": stdout
                }
            else:
                # Check if already installed
                if "already installed" in stderr.lower():
                    if ctx:
                        await ctx.report_progress(100, 100)
                        await ctx.info(f"Library '{library_name}' is already installed")
                    return {
                        "success": True,
                        "message": f"Library '{library_name}' is already installed",
                        "output": stderr
                    }
                if ctx:
                    await ctx.error(f"Installation failed for library '{library_name}'")
                return {
                    "error": "Installation failed",
                    "library": library_name,
                    "stderr": stderr
                }

        except asyncio.TimeoutError:
            if ctx:
                await ctx.error(f"Installation timed out after {self.config.command_timeout * 2} seconds")
            return {"error": f"Installation timed out after {self.config.command_timeout * 2} seconds"}
        except Exception as e:
            log.exception(f"Library installation failed: {e}")
            if ctx:
                await ctx.error(f"Installation failed: {str(e)}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_uninstall_library",
        description="Uninstall an Arduino library",
        annotations=ToolAnnotations(
            title="Uninstall Arduino Library",
            destructiveHint=True,
            idempotentHint=True,
        )
    )
    async def uninstall_library(
        self,
        ctx: Context | None,
        library_name: str
    ) -> dict[str, Any]:
        """Uninstall an Arduino library"""

        try:
            cmd = [
                self.arduino_cli_path,
                "lib", "uninstall",
                library_name
            ]

            log.info(f"Uninstalling library: {library_name}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Library '{library_name}' uninstalled successfully",
                    "output": result.stdout
                }
            else:
                return {
                    "error": "Uninstallation failed",
                    "library": library_name,
                    "stderr": result.stderr
                }

        except subprocess.TimeoutExpired:
            return {"error": f"Uninstallation timed out after {self.config.command_timeout} seconds"}
        except Exception as e:
            log.exception(f"Library uninstallation failed: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_list_library_examples",
        description="List examples from an installed library",
        annotations=ToolAnnotations(
            title="List Library Examples",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def list_library_examples(
        self,
        ctx: Context | None,
        library_name: str
    ) -> dict[str, Any]:
        """List examples from an installed Arduino library"""

        try:
            # Find library directory
            libraries_dir = self.arduino_user_dir / "libraries"
            if not libraries_dir.exists():
                return {"error": "No libraries directory found"}

            # Search for library (case-insensitive)
            library_dir = None
            for item in libraries_dir.iterdir():
                if item.is_dir() and item.name.lower() == library_name.lower():
                    library_dir = item
                    break

            # Fuzzy search if exact match not found and fuzzy search available
            if not library_dir and self.fuzzy_available:
                best_match = None
                best_score = 0
                for item in libraries_dir.iterdir():
                    if item.is_dir():
                        score = self.fuzz.ratio(library_name.lower(), item.name.lower())
                        if score > best_score and score >= self.config.fuzzy_search_threshold:
                            best_score = score
                            best_match = item

                if best_match:
                    library_dir = best_match
                    log.info(f"Fuzzy matched '{library_name}' to '{best_match.name}' (score: {best_score})")

            if not library_dir:
                return {"error": f"Library '{library_name}' not found"}

            # Find examples directory
            examples_dir = library_dir / "examples"
            if not examples_dir.exists():
                return {
                    "message": f"Library '{library_dir.name}' has no examples",
                    "library": library_dir.name,
                    "examples": []
                }

            # List all examples
            examples = []
            for example in examples_dir.iterdir():
                if example.is_dir():
                    # Look for .ino file
                    ino_files = list(example.glob("*.ino"))
                    if ino_files:
                        examples.append({
                            "name": example.name,
                            "path": str(example),
                            "ino_file": str(ino_files[0]),
                            "description": self._get_example_description(ino_files[0])
                        })

            return {
                "success": True,
                "library": library_dir.name,
                "count": len(examples),
                "examples": examples
            }

        except Exception as e:
            log.exception(f"Failed to list library examples: {e}")
            return {"error": str(e)}

    async def _get_installed_libraries(self) -> list[dict[str, Any]]:
        """Get list of installed libraries"""
        try:
            cmd = [
                self.arduino_cli_path,
                "lib", "list",
                "--format", "json"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get('installed_libraries', [])
            return []

        except Exception as e:
            log.error(f"Failed to get installed libraries: {e}")
            return []

    def _get_example_description(self, ino_file: Path) -> str:
        """Extract description from example .ino file"""
        try:
            content = ino_file.read_text()
            lines = content.splitlines()[:10]  # Check first 10 lines

            # Look for description in comments
            description = ""
            for line in lines:
                line = line.strip()
                if line.startswith("//"):
                    desc_line = line[2:].strip()
                    if desc_line and not desc_line.startswith("*"):
                        description = desc_line
                        break
                elif line.startswith("/*"):
                    # Multi-line comment
                    for next_line in lines[lines.index(line) + 1:]:
                        if "*/" in next_line:
                            break
                        desc_line = next_line.strip().lstrip("*").strip()
                        if desc_line:
                            description = desc_line
                            break
                    break

            return description or "No description available"

        except Exception:
            return "No description available"
