"""
Advanced Arduino Compilation Component
Provides advanced compile options, build analysis, and cache management
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from pydantic import Field

logger = logging.getLogger(__name__)


class ArduinoCompileAdvanced(MCPMixin):
    """Advanced compilation features for Arduino"""

    def __init__(self, config):
        """Initialize advanced compilation manager"""
        self.config = config
        self.cli_path = config.arduino_cli_path
        self.sketch_dir = Path(config.sketch_dir).expanduser()
        self.build_cache_dir = Path.home() / ".arduino" / "build-cache"

    async def _run_arduino_cli(self, args: list[str], capture_output: bool = True) -> dict[str, Any]:
        """Run Arduino CLI command and return result"""
        cmd = [self.cli_path] + args

        try:
            if capture_output:
                # Add --json flag for structured output where applicable
                if '--json' not in args and '--format' not in ' '.join(args):
                    # Some commands support JSON
                    if args[0] in ["compile", "upload", "board", "lib", "core", "config"]:
                        cmd.append('--json')

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    env={**os.environ, "ARDUINO_DIRECTORIES_DATA": str(Path.home() / ".arduino15")}
                )

                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout
                    try:
                        error_data = json.loads(error_msg)
                        return {"success": False, "error": error_data.get("error", error_msg)}
                    except:
                        return {"success": False, "error": error_msg}

                # Parse JSON output if possible
                try:
                    data = json.loads(result.stdout)
                    return {"success": True, "data": data}
                except json.JSONDecodeError:
                    return {"success": True, "output": result.stdout}
            else:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return {"success": True, "process": process}

        except Exception as e:
            logger.error(f"Arduino CLI error: {e}")
            return {"success": False, "error": str(e)}

    @mcp_tool(
        name="arduino_compile_advanced",
        description="Compile sketch with advanced options and build properties"
    )
    async def compile_advanced(
        self,
        sketch_name: str = Field(..., description="Name of the sketch to compile"),
        fqbn: str | None = Field(None, description="Board FQBN (auto-detect if not provided)"),
        build_properties: dict[str, str] | None = Field(None, description="Custom build properties"),
        build_cache_path: str | None = Field(None, description="Custom build cache directory"),
        build_path: str | None = Field(None, description="Custom build output directory"),
        export_binaries: bool = Field(False, description="Export compiled binaries to sketch folder"),
        libraries: list[str] | None = Field(None, description="Additional libraries to include"),
        optimize_for_debug: bool = Field(False, description="Optimize for debugging"),
        preprocess_only: bool = Field(False, description="Only run preprocessor"),
        show_properties: bool = Field(False, description="Show all build properties"),
        verbose: bool = Field(False, description="Verbose output"),
        warnings: str = Field("default", description="Warning level: none, default, more, all"),
        vid_pid: str | None = Field(None, description="USB VID/PID for board detection"),
        jobs: int | None = Field(None, description="Number of parallel jobs"),
        clean: bool = Field(False, description="Clean build directory before compile"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """
        Compile Arduino sketch with advanced options

        Provides fine-grained control over the compilation process including
        custom build properties, optimization settings, and parallel compilation.
        """
        sketch_path = self.sketch_dir / sketch_name

        if not sketch_path.exists():
            return {"success": False, "error": f"Sketch '{sketch_name}' not found"}

        args = ["compile", str(sketch_path)]

        # Add FQBN if provided
        if fqbn:
            args.extend(["--fqbn", fqbn])

        # Add build properties
        if build_properties:
            for key, value in build_properties.items():
                args.extend(["--build-property", f"{key}={value}"])

        # Build paths
        if build_cache_path:
            args.extend(["--build-cache-path", build_cache_path])
        if build_path:
            args.extend(["--build-path", build_path])

        # Export binaries
        if export_binaries:
            args.append("--export-binaries")

        # Libraries
        if libraries:
            for lib in libraries:
                args.extend(["--libraries", lib])

        # Optimization
        if optimize_for_debug:
            args.append("--optimize-for-debug")

        # Preprocessing
        if preprocess_only:
            args.append("--preprocess")

        # Show properties
        if show_properties:
            args.append("--show-properties")

        # Verbose
        if verbose:
            args.append("--verbose")

        # Warnings
        if warnings != "default":
            args.extend(["--warnings", warnings])

        # VID/PID
        if vid_pid:
            args.extend(["--vid-pid", vid_pid])

        # Parallel jobs
        if jobs:
            args.extend(["--jobs", str(jobs)])

        # Clean build
        if clean:
            args.append("--clean")

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        # Check if we got JSON data or plain output
        data = result.get("data", {})

        # If no data but we have output, compilation succeeded with non-JSON output
        if not data and result.get("output"):
            # Parse information from text output if available
            output = result.get("output", "")

            # Try to extract build path from output (usually in temp directory)
            import re
            build_path_match = re.search(r'Using.*?sketch.*?directory:\s*(.+)', output)
            if build_path_match:
                build_path = build_path_match.group(1).strip()
            else:
                # Default Arduino build path
                import hashlib
                sketch_hash = hashlib.md5(str(sketch_path).encode()).hexdigest().upper()
                build_path = str(Path.home() / ".cache" / "arduino" / "sketches" / sketch_hash)

            # Create minimal compile info when JSON is not available
            compile_info = {
                "sketch": sketch_name,
                "fqbn": fqbn,
                "build_path": build_path if Path(build_path).exists() else None,
                "libraries_used": [],
                "warnings": [],
                "build_properties": build_properties or {}
            }
        else:
            # Handle both direct data and builder_result structures
            builder_result = data.get("builder_result", data)

            # Extract compilation info
            compile_info = {
                "sketch": sketch_name,
                "fqbn": fqbn or builder_result.get("board_platform", {}).get("id"),
                "build_path": builder_result.get("build_path"),
                "libraries_used": [],
                "warnings": [],
                "build_properties": build_properties or {}
            }

            # Parse libraries used
            if "used_libraries" in builder_result:
                for lib in builder_result["used_libraries"]:
                    lib_info = {
                        "name": lib.get("name"),
                        "version": lib.get("version"),
                        "location": lib.get("location"),
                        "source_dir": lib.get("source_dir")
                    }
                    compile_info["libraries_used"].append(lib_info)

            # Get size info if available
            if "executable_sections_size" in builder_result:
                compile_info["size_info"] = builder_result["executable_sections_size"]

        # Extract binary info if exported
        if export_binaries:
            binary_dir = sketch_path / "build"
            if binary_dir.exists():
                binaries = []
                for file in binary_dir.glob("*"):
                    if file.suffix in [".hex", ".bin", ".elf"]:
                        binaries.append({
                            "name": file.name,
                            "path": str(file),
                            "size": file.stat().st_size
                        })
                compile_info["exported_binaries"] = binaries

        return {
            "success": True,
            **compile_info,
            "message": "Compilation successful"
        }

    @mcp_tool(
        name="arduino_size_analysis",
        description="Analyze compiled binary size and memory usage"
    )
    async def analyze_size(
        self,
        sketch_name: str = Field(..., description="Name of the sketch"),
        fqbn: str | None = Field(None, description="Board FQBN"),
        build_path: str | None = Field(None, description="Build directory path"),
        detailed: bool = Field(True, description="Show detailed section breakdown"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """Analyze compiled sketch size and memory usage"""

        # First compile to ensure we have a binary
        compile_result = await self.compile_advanced(
            sketch_name=sketch_name,
            fqbn=fqbn,
            build_path=build_path,
            build_properties=None,
            build_cache_path=None,
            export_binaries=False,
            libraries=None,
            optimize_for_debug=False,
            preprocess_only=False,
            show_properties=False,
            verbose=False,
            warnings="default",
            vid_pid=None,
            jobs=None,
            clean=False,
            ctx=ctx
        )

        if not compile_result["success"]:
            return compile_result

        # Get the build path
        if not build_path:
            build_path = compile_result.get("build_path")

        if not build_path:
            return {"success": False, "error": "Build path not found"}

        # Find the ELF file
        build_dir = Path(build_path)
        elf_files = list(build_dir.glob("*.elf"))

        if not elf_files:
            return {"success": False, "error": "No compiled binary found"}

        elf_file = elf_files[0]

        # Run size analysis using avr-size or arm-none-eabi-size
        size_cmd = None
        if fqbn and "avr" in fqbn:
            size_cmd = ["avr-size", "-A", str(elf_file)]
        elif fqbn and ("esp32" in fqbn or "esp8266" in fqbn):
            size_cmd = ["xtensa-esp32-elf-size", "-A", str(elf_file)]
        else:
            # Try generic size command
            size_cmd = ["size", "-A", str(elf_file)]

        try:
            result = subprocess.run(
                size_cmd,
                capture_output=True,
                text=True,
                check=True
            )

            # Parse size output
            lines = result.stdout.strip().split('\n')
            sections = {}
            total_flash = 0
            total_ram = 0

            for line in lines[2:]:  # Skip header
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        section = parts[0]
                        size = int(parts[1])
                        sections[section] = size

                        # Calculate flash and RAM usage
                        if section in [".text", ".data", ".rodata"]:
                            total_flash += size
                        elif section in [".data", ".bss", ".noinit"]:
                            total_ram += size

            # Get board memory limits
            memory_limits = self._get_board_memory_limits(fqbn)

            size_info = {
                "sketch": sketch_name,
                "binary": str(elf_file),
                "sections": sections if detailed else None,
                "flash_used": total_flash,
                "ram_used": total_ram,
                "flash_total": memory_limits.get("flash"),
                "ram_total": memory_limits.get("ram"),
                "flash_percentage": (total_flash / memory_limits["flash"] * 100) if memory_limits.get("flash") else None,
                "ram_percentage": (total_ram / memory_limits["ram"] * 100) if memory_limits.get("ram") else None
            }

            # Add warnings if usage is high
            warnings = []
            if size_info["flash_percentage"] and size_info["flash_percentage"] > 90:
                warnings.append(f"Flash usage is {size_info['flash_percentage']:.1f}% - approaching limit!")
            if size_info["ram_percentage"] and size_info["ram_percentage"] > 75:
                warnings.append(f"RAM usage is {size_info['ram_percentage']:.1f}% - may cause stability issues!")

            size_info["warnings"] = warnings

            return {
                "success": True,
                **size_info
            }

        except subprocess.CalledProcessError as e:
            return {"success": False, "error": f"Size analysis failed: {e.stderr}"}
        except FileNotFoundError:
            return {"success": False, "error": "Size analysis tool not found. Install avr-size or xtensa-esp32-elf-size"}

    def _get_board_memory_limits(self, fqbn: str | None) -> dict[str, int]:
        """Get memory limits for common boards"""
        memory_map = {
            "arduino:avr:uno": {"flash": 32256, "ram": 2048},
            "arduino:avr:mega": {"flash": 253952, "ram": 8192},
            "arduino:avr:nano": {"flash": 30720, "ram": 2048},
            "arduino:avr:leonardo": {"flash": 28672, "ram": 2560},
            "esp32:esp32:esp32": {"flash": 1310720, "ram": 327680},
            "esp8266:esp8266:generic": {"flash": 1044464, "ram": 81920},
            "arduino:samd:mkr1000": {"flash": 262144, "ram": 32768},
            "arduino:samd:nano_33_iot": {"flash": 262144, "ram": 32768},
        }

        if fqbn:
            # Try exact match first
            if fqbn in memory_map:
                return memory_map[fqbn]

            # Try partial match
            for board, limits in memory_map.items():
                if board.split(":")[1] in fqbn:  # Match architecture
                    return limits

        # Default values
        return {"flash": 32768, "ram": 2048}

    @mcp_tool(
        name="arduino_cache_clean",
        description="Clean the Arduino build cache"
    )
    async def clean_cache(
        self,
        ctx: Context = None
    ) -> dict[str, Any]:
        """Clean Arduino build cache to free disk space"""
        args = ["cache", "clean"]

        result = await self._run_arduino_cli(args)

        if result["success"]:
            # Calculate freed space
            cache_dir = Path.home() / ".arduino15" / "build-cache"
            freed_space = 0

            if cache_dir.exists():
                # Cache should be empty now
                for item in cache_dir.rglob("*"):
                    if item.is_file():
                        freed_space += item.stat().st_size

            return {
                "success": True,
                "message": "Build cache cleaned successfully",
                "cache_directory": str(cache_dir),
                "freed_space_mb": freed_space / (1024 * 1024)
            }

        return result

    @mcp_tool(
        name="arduino_build_show_properties",
        description="Show all build properties for a board"
    )
    async def show_build_properties(
        self,
        fqbn: str = Field(..., description="Board FQBN"),
        sketch_name: str | None = Field(None, description="Sketch to get properties for"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """Show all build properties used during compilation"""

        args = ["compile", "--fqbn", fqbn, "--show-properties"]

        # Use a dummy sketch or provided one
        if sketch_name:
            sketch_path = self.sketch_dir / sketch_name
            if sketch_path.exists():
                args.append(str(sketch_path))
        else:
            # Create temporary sketch
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_sketch = Path(tmpdir) / "temp" / "temp.ino"
                tmp_sketch.parent.mkdir(parents=True)
                tmp_sketch.write_text("void setup() {} void loop() {}")
                args.append(str(tmp_sketch.parent))

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        # Parse properties from output
        properties = {}
        output = result.get("output", "")

        for line in output.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                properties[key.strip()] = value.strip()

        # Categorize properties
        categorized = {
            "build": {},
            "compiler": {},
            "tools": {},
            "runtime": {},
            "other": {}
        }

        for key, value in properties.items():
            if key.startswith("build."):
                categorized["build"][key] = value
            elif key.startswith("compiler."):
                categorized["compiler"][key] = value
            elif key.startswith("tools."):
                categorized["tools"][key] = value
            elif key.startswith("runtime."):
                categorized["runtime"][key] = value
            else:
                categorized["other"][key] = value

        return {
            "success": True,
            "fqbn": fqbn,
            "total_properties": len(properties),
            "properties": categorized,
            "all_properties": properties
        }

    @mcp_tool(
        name="arduino_export_compiled_binary",
        description="Export compiled binary files to a specific location"
    )
    async def export_binary(
        self,
        sketch_name: str = Field(..., description="Name of the sketch"),
        output_dir: str | None = Field(None, description="Directory to export to (default: sketch folder)"),
        fqbn: str | None = Field(None, description="Board FQBN"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """Export compiled binary files (.hex, .bin, .elf)"""

        # Compile with export flag
        result = await self.compile_advanced(
            sketch_name=sketch_name,
            fqbn=fqbn,
            export_binaries=True,
            ctx=ctx
        )

        if not result["success"]:
            return result

        # Move binaries to specified location if needed
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            exported = []
            for binary in result.get("exported_binaries", []):
                src = Path(binary["path"])
                dst = output_path / binary["name"]
                shutil.copy2(src, dst)
                exported.append({
                    "name": binary["name"],
                    "path": str(dst),
                    "size": binary["size"]
                })

            return {
                "success": True,
                "sketch": sketch_name,
                "output_directory": str(output_path),
                "exported_files": exported
            }

        return {
            "success": True,
            "sketch": sketch_name,
            "exported_files": result.get("exported_binaries", [])
        }
