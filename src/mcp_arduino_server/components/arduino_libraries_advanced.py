"""
Advanced Arduino Library Management Component
Provides dependency checking, version management, and library operations
"""

import json
import os
import re
from typing import List, Dict, Optional, Any
from pathlib import Path
import subprocess
import logging

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from pydantic import Field

logger = logging.getLogger(__name__)


class ArduinoLibrariesAdvanced(MCPMixin):
    """Advanced library management features for Arduino"""

    def __init__(self, config):
        """Initialize advanced library manager"""
        self.config = config
        self.cli_path = config.arduino_cli_path
        self.sketch_dir = Path(config.sketch_dir).expanduser()

    async def _run_arduino_cli(self, args: List[str], capture_output: bool = True) -> Dict[str, Any]:
        """Run Arduino CLI command and return result"""
        cmd = [self.cli_path] + args

        try:
            if capture_output:
                # Add --json flag for structured output
                if '--json' not in args:
                    cmd.append('--json')

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout
                    # Try to parse JSON error
                    try:
                        error_data = json.loads(error_msg)
                        return {"success": False, "error": error_data.get("error", error_msg)}
                    except:
                        return {"success": False, "error": error_msg}

                # Parse JSON output
                try:
                    data = json.loads(result.stdout)
                    return {"success": True, "data": data}
                except json.JSONDecodeError:
                    # Fallback for non-JSON output
                    return {"success": True, "output": result.stdout}
            else:
                # For streaming operations
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
        name="arduino_lib_deps",
        description="Check library dependencies and identify missing libraries"
    )
    async def check_dependencies(
        self,
        library_name: str = Field(..., description="Library name to check dependencies for"),
        fqbn: Optional[str] = Field(None, description="Board FQBN to check compatibility"),
        check_installed: bool = Field(True, description="Check if dependencies are installed"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """
        Check library dependencies and identify missing libraries

        Returns dependency tree with status of each dependency
        """
        args = ["lib", "deps", library_name]

        if fqbn:
            args.extend(["--fqbn", fqbn])

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        # Parse dependency information
        data = result.get("data", {})

        # Structure the dependency tree
        deps_info = {
            "library": library_name,
            "dependencies": [],
            "missing": [],
            "installed": [],
            "conflicts": []
        }

        # Process dependencies from the JSON output
        if isinstance(data, dict):
            # Extract dependency information
            all_deps = data.get("dependencies", [])

            # Debug: Log what we're processing
            logger.debug(f"Processing deps for {library_name}: {all_deps}")

            # Filter out self-reference and process actual dependencies
            for dep in all_deps:
                dep_name = dep.get("name", "")

                # Skip self-reference (library listing itself)
                if dep_name == library_name:
                    logger.debug(f"Skipping self-reference: {dep_name}")
                    continue

                # Determine if installed based on presence of version_installed
                is_installed = bool(dep.get("version_installed"))

                dep_info = {
                    "name": dep_name,
                    "version_required": dep.get("version_required"),
                    "version_installed": dep.get("version_installed"),
                    "installed": is_installed
                }

                deps_info["dependencies"].append(dep_info)

                if is_installed:
                    deps_info["installed"].append(dep_name)
                else:
                    deps_info["missing"].append(dep_name)

                # Check for version conflicts
                if is_installed and dep_info["version_required"]:
                    # Compare version strings after normalizing
                    req_version = str(dep_info["version_required"]).strip()
                    inst_version = str(dep_info["version_installed"]).strip()
                    # Check if versions are compatible (installed >= required)
                    if req_version and inst_version and req_version != inst_version:
                        deps_info["conflicts"].append({
                            "library": dep_name,
                            "required": req_version,
                            "installed": inst_version
                        })

        return {
            "success": True,
            "library": library_name,
            "fqbn": fqbn,
            "dependencies": deps_info["dependencies"],
            "missing_count": len(deps_info["missing"]),
            "missing_libraries": deps_info["missing"],
            "installed_count": len(deps_info["installed"]),
            "installed_libraries": deps_info["installed"],
            "conflicts": deps_info["conflicts"],
            "has_conflicts": len(deps_info["conflicts"]) > 0,
            "all_satisfied": len(deps_info["missing"]) == 0 and len(deps_info["conflicts"]) == 0
        }

    @mcp_tool(
        name="arduino_lib_download",
        description="Download libraries without installing them"
    )
    async def download_library(
        self,
        library_name: str = Field(..., description="Library name to download"),
        version: Optional[str] = Field(None, description="Specific version to download"),
        download_dir: Optional[str] = Field(None, description="Directory to download to"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Download library archives without installation"""
        args = ["lib", "download", library_name]

        if version:
            args.append(f"{library_name}@{version}")
        else:
            args.append(library_name)

        if download_dir:
            args.extend(["--download-dir", download_dir])

        result = await self._run_arduino_cli(args)

        if result["success"]:
            # Find downloaded file
            download_path = download_dir or os.path.expanduser("~/Downloads")
            pattern = f"{library_name}*.zip"

            return {
                "success": True,
                "library": library_name,
                "version": version,
                "download_dir": download_path,
                "message": f"Library downloaded to {download_path}"
            }

        return result

    @mcp_tool(
        name="arduino_lib_list",
        description="List installed libraries with version information"
    )
    async def list_libraries(
        self,
        updatable: bool = Field(False, description="Show only updatable libraries"),
        all_versions: bool = Field(False, description="Show all available versions"),
        fqbn: Optional[str] = Field(None, description="Filter by board compatibility"),
        name_filter: Optional[str] = Field(None, description="Filter by library name pattern"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """List installed libraries with detailed information"""
        args = ["lib", "list"]

        if updatable:
            args.append("--updatable")

        if all_versions:
            args.append("--all")

        if fqbn:
            args.extend(["--fqbn", fqbn])

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        data = result.get("data", {})
        installed_libs = data.get("installed_libraries", [])

        # Process and filter libraries
        libraries = []
        for lib in installed_libs:
            lib_info = {
                "name": lib.get("library", {}).get("name"),
                "version": lib.get("library", {}).get("version"),
                "author": lib.get("library", {}).get("author"),
                "maintainer": lib.get("library", {}).get("maintainer"),
                "sentence": lib.get("library", {}).get("sentence"),
                "paragraph": lib.get("library", {}).get("paragraph"),
                "website": lib.get("library", {}).get("website"),
                "category": lib.get("library", {}).get("category"),
                "architectures": lib.get("library", {}).get("architectures", []),
                "types": lib.get("library", {}).get("types", []),
                "install_dir": lib.get("library", {}).get("install_dir"),
                "source_dir": lib.get("library", {}).get("source_dir"),
                "is_legacy": lib.get("library", {}).get("is_legacy", False),
                "in_development": lib.get("library", {}).get("in_development", False),
                "available_version": lib.get("release", {}).get("version") if lib.get("release") else None,
                "updatable": lib.get("release", {}).get("version") != lib.get("library", {}).get("version") if lib.get("release") else False
            }

            # Apply name filter if provided
            if name_filter:
                if name_filter.lower() not in lib_info["name"].lower():
                    continue

            libraries.append(lib_info)

        # Sort by name
        libraries.sort(key=lambda x: x["name"].lower())

        # Count statistics
        stats = {
            "total": len(libraries),
            "updatable": sum(1 for lib in libraries if lib["updatable"]),
            "legacy": sum(1 for lib in libraries if lib["is_legacy"]),
            "in_development": sum(1 for lib in libraries if lib["in_development"])
        }

        return {
            "success": True,
            "libraries": libraries,
            "statistics": stats,
            "filtered": name_filter is not None,
            "fqbn": fqbn
        }

    @mcp_tool(
        name="arduino_lib_upgrade",
        description="Upgrade installed libraries to latest versions"
    )
    async def upgrade_libraries(
        self,
        library_names: Optional[List[str]] = Field(None, description="Specific libraries to upgrade (None = all)"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Upgrade one or more libraries to their latest versions"""
        args = ["lib", "upgrade"]

        if library_names:
            args.extend(library_names)
        else:
            # Upgrade all libraries
            args.append("--all")

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        # Parse upgrade results
        data = result.get("data", {})

        upgraded = []
        failed = []

        # Process upgrade results
        if "upgraded_libraries" in data:
            for lib in data["upgraded_libraries"]:
                upgraded.append({
                    "name": lib.get("name"),
                    "old_version": lib.get("old_version"),
                    "new_version": lib.get("new_version")
                })

        if "failed_libraries" in data:
            for lib in data["failed_libraries"]:
                failed.append({
                    "name": lib.get("name"),
                    "error": lib.get("error")
                })

        return {
            "success": True,
            "upgraded_count": len(upgraded),
            "upgraded_libraries": upgraded,
            "failed_count": len(failed),
            "failed_libraries": failed,
            "all_libraries": library_names is None
        }

    @mcp_tool(
        name="arduino_update_index",
        description="Update the libraries and boards index"
    )
    async def update_index(
        self,
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Update Arduino libraries and boards package index"""
        # Update libraries index
        lib_result = await self._run_arduino_cli(["lib", "update-index"])

        # Update cores index
        core_result = await self._run_arduino_cli(["core", "update-index"])

        success = lib_result["success"] and core_result["success"]

        return {
            "success": success,
            "libraries_updated": lib_result["success"],
            "cores_updated": core_result["success"],
            "libraries_error": lib_result.get("error") if not lib_result["success"] else None,
            "cores_error": core_result.get("error") if not core_result["success"] else None,
            "message": "Indexes updated successfully" if success else "Some indexes failed to update"
        }

    @mcp_tool(
        name="arduino_outdated",
        description="List outdated libraries and cores"
    )
    async def check_outdated(
        self,
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Check for outdated libraries and cores"""
        result = await self._run_arduino_cli(["outdated"])

        if not result["success"]:
            return result

        data = result.get("data", {})

        outdated_info = {
            "libraries": [],
            "platforms": []
        }

        # Process outdated libraries
        if "libraries" in data:
            for lib in data["libraries"]:
                outdated_info["libraries"].append({
                    "name": lib.get("name"),
                    "installed": lib.get("installed", {}).get("version"),
                    "available": lib.get("available", {}).get("version"),
                    "location": lib.get("location")
                })

        # Process outdated platforms (cores)
        if "platforms" in data:
            for platform in data["platforms"]:
                outdated_info["platforms"].append({
                    "id": platform.get("id"),
                    "installed": platform.get("installed"),
                    "latest": platform.get("latest")
                })

        return {
            "success": True,
            "outdated_libraries": outdated_info["libraries"],
            "outdated_platforms": outdated_info["platforms"],
            "library_count": len(outdated_info["libraries"]),
            "platform_count": len(outdated_info["platforms"]),
            "total_outdated": len(outdated_info["libraries"]) + len(outdated_info["platforms"])
        }

    @mcp_tool(
        name="arduino_lib_examples",
        description="List examples from installed libraries"
    )
    async def list_examples(
        self,
        library_name: Optional[str] = Field(None, description="Filter examples by library name"),
        fqbn: Optional[str] = Field(None, description="Filter by board compatibility"),
        with_description: bool = Field(True, description="Include example descriptions"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """List all examples from installed libraries"""
        args = ["lib", "examples"]

        if library_name:
            args.append(library_name)

        if fqbn:
            args.extend(["--fqbn", fqbn])

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        data = result.get("data", {})
        examples = data.get("examples", [])

        # Process examples
        example_list = []
        for example in examples:
            example_info = {
                "library": example.get("library", {}).get("name"),
                "library_version": example.get("library", {}).get("version"),
                "name": example.get("name"),
                "path": example.get("path"),
                "sketch_path": example.get("sketch", {}).get("main_file") if example.get("sketch") else None,
                "compatible": example.get("compatible_with_board", True) if fqbn else None
            }

            # Read example description if requested
            if with_description and example_info["sketch_path"]:
                try:
                    sketch_file = Path(example_info["sketch_path"])
                    if sketch_file.exists():
                        with open(sketch_file, 'r') as f:
                            # Read first comment block as description
                            content = f.read(500)  # First 500 chars
                            if content.startswith("/*"):
                                end_idx = content.find("*/")
                                if end_idx > 0:
                                    example_info["description"] = content[2:end_idx].strip()
                except:
                    pass

            example_list.append(example_info)

        # Group by library
        by_library = {}
        for example in example_list:
            lib_name = example["library"]
            if lib_name not in by_library:
                by_library[lib_name] = []
            by_library[lib_name].append(example)

        return {
            "success": True,
            "total_examples": len(example_list),
            "library_count": len(by_library),
            "examples": example_list,
            "by_library": by_library,
            "filtered_by": {
                "library": library_name,
                "fqbn": fqbn
            }
        }

    @mcp_tool(
        name="arduino_lib_install_missing",
        description="Install all missing dependencies for a library or sketch"
    )
    async def install_missing_dependencies(
        self,
        library_name: Optional[str] = Field(None, description="Library to install dependencies for"),
        sketch_name: Optional[str] = Field(None, description="Sketch to analyze and install dependencies for"),
        dry_run: bool = Field(False, description="Only show what would be installed"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Install all missing dependencies automatically"""

        to_install = []

        # Check library dependencies
        if library_name:
            deps_result = await self.check_dependencies(library_name=library_name, ctx=ctx)
            if deps_result["success"]:
                to_install.extend(deps_result["missing_libraries"])

        # Analyze sketch dependencies
        if sketch_name:
            sketch_path = self.sketch_dir / sketch_name / f"{sketch_name}.ino"
            if sketch_path.exists():
                # Parse includes from sketch
                with open(sketch_path, 'r') as f:
                    content = f.read()
                    includes = re.findall(r'#include\s+[<"]([^>"]+)[>"]', content)

                # Map common includes to library names
                library_map = {
                    "WiFi.h": "WiFi",
                    "Ethernet.h": "Ethernet",
                    "SPI.h": None,  # Built-in
                    "Wire.h": None,  # Built-in
                    "Servo.h": "Servo",
                    "ArduinoJson.h": "ArduinoJson",
                    "PubSubClient.h": "PubSubClient",
                    "Adafruit_Sensor.h": "Adafruit Unified Sensor",
                    "DHT.h": "DHT sensor library",
                    "LiquidCrystal_I2C.h": "LiquidCrystal I2C",
                    "FastLED.h": "FastLED",
                    "NeoPixelBus.h": "NeoPixelBus",
                }

                for include in includes:
                    lib_name = library_map.get(include)
                    if lib_name and lib_name not in to_install:
                        # Check if already installed
                        list_result = await self.list_libraries(name_filter=lib_name, ctx=ctx)
                        if not list_result["libraries"]:
                            to_install.append(lib_name)

        # Remove duplicates
        to_install = list(set(to_install))

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "would_install": to_install,
                "count": len(to_install)
            }

        # Install missing libraries
        installed = []
        failed = []

        for lib in to_install:
            args = ["lib", "install", lib]
            result = await self._run_arduino_cli(args)

            if result["success"]:
                installed.append(lib)
            else:
                failed.append({
                    "library": lib,
                    "error": result.get("error")
                })

        return {
            "success": len(failed) == 0,
            "installed_count": len(installed),
            "installed_libraries": installed,
            "failed_count": len(failed),
            "failed_libraries": failed,
            "all_dependencies_satisfied": len(failed) == 0
        }