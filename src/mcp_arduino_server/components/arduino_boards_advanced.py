"""
Advanced Arduino Board Management Component
Provides board details, discovery, and attachment features
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from pydantic import Field

logger = logging.getLogger(__name__)


class ArduinoBoardsAdvanced(MCPMixin):
    """Advanced board management features for Arduino"""

    def __init__(self, config):
        """Initialize advanced board manager"""
        self.config = config
        self.cli_path = config.arduino_cli_path
        self.sketch_dir = Path(config.sketch_dir).expanduser()

    async def _run_arduino_cli(self, args: list[str], capture_output: bool = True) -> dict[str, Any]:
        """Run Arduino CLI command and return result"""
        cmd = [self.cli_path] + args

        try:
            if capture_output:
                # Add --json flag for structured output
                if '--json' not in args and '--format' not in ' '.join(args):
                    cmd.append('--json')

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout
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
        name="arduino_board_details",
        description="Get detailed information about a specific board"
    )
    async def get_board_details(
        self,
        fqbn: str = Field(..., description="Fully Qualified Board Name (e.g., arduino:avr:uno)"),
        list_programmers: bool = Field(False, description="Include available programmers"),
        show_properties: bool = Field(True, description="Show all board properties"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """Get comprehensive details about a specific board"""
        args = ["board", "details", "--fqbn", fqbn]

        if list_programmers:
            args.append("--list-programmers")

        if show_properties:
            args.append("--show-properties=expanded")

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        data = result.get("data", {})

        # Structure board information
        board_info = {
            "fqbn": fqbn,
            "name": data.get("name"),
            "version": data.get("version"),
            "properties_id": data.get("properties_id"),
            "official": data.get("official", False),
            "package": data.get("package", {}).get("name"),
            "platform": {
                "architecture": data.get("platform", {}).get("architecture"),
                "category": data.get("platform", {}).get("category"),
                "boards": data.get("platform", {}).get("boards", [])
            }
        }

        # Extract configuration options
        config_options = []
        if "config_options" in data:
            for option in data["config_options"]:
                opt_info = {
                    "option": option.get("option"),
                    "option_label": option.get("option_label"),
                    "values": []
                }
                for value in option.get("values", []):
                    opt_info["values"].append({
                        "value": value.get("value"),
                        "value_label": value.get("value_label"),
                        "selected": value.get("selected", False)
                    })
                config_options.append(opt_info)

        board_info["config_options"] = config_options

        # Extract programmers if requested
        if list_programmers and "programmers" in data:
            board_info["programmers"] = data["programmers"]

        # Extract properties
        if show_properties and "properties" in data:
            board_info["properties"] = data["properties"]

        # Extract tools dependencies
        if "tools_dependencies" in data:
            board_info["tools"] = data["tools_dependencies"]

        return {
            "success": True,
            **board_info
        }

    @mcp_tool(
        name="arduino_board_listall",
        description="List all available boards from installed cores"
    )
    async def list_all_boards(
        self,
        search_filter: str | None = Field(None, description="Filter boards by name or FQBN"),
        show_hidden: bool = Field(False, description="Show hidden boards"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """List all available boards from all installed platforms"""
        args = ["board", "listall"]

        if search_filter:
            args.append(search_filter)

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        data = result.get("data", {})
        boards = data.get("boards", [])

        # Process board list
        board_list = []
        platforms = set()

        for board in boards:
            # Skip hidden boards unless requested
            if board.get("hidden", False) and not show_hidden:
                continue

            board_info = {
                "name": board.get("name"),
                "fqbn": board.get("fqbn"),
                "platform": board.get("platform", {}).get("id"),
                "package": board.get("platform", {}).get("maintainer"),
                "architecture": board.get("platform", {}).get("architecture"),
                "version": board.get("platform", {}).get("installed_version"),
                "official": board.get("platform", {}).get("maintainer") == "Arduino"
            }

            board_list.append(board_info)
            platforms.add(board_info["platform"])

        # Sort by platform and name
        board_list.sort(key=lambda x: (x["platform"], x["name"]))

        # Group by platform
        by_platform = {}
        for board in board_list:
            platform = board["platform"]
            if platform not in by_platform:
                by_platform[platform] = []
            by_platform[platform].append(board)

        # Count statistics
        stats = {
            "total_boards": len(board_list),
            "platforms": len(platforms),
            "official_boards": sum(1 for b in board_list if b["official"]),
            "third_party_boards": sum(1 for b in board_list if not b["official"])
        }

        return {
            "success": True,
            "boards": board_list,
            "by_platform": by_platform,
            "statistics": stats,
            "filtered": search_filter is not None
        }

    @mcp_tool(
        name="arduino_board_attach",
        description="Attach a board to a sketch for persistent configuration"
    )
    async def attach_board(
        self,
        sketch_name: str = Field(..., description="Sketch name to attach board to"),
        port: str | None = Field(None, description="Port where board is connected"),
        fqbn: str | None = Field(None, description="Board FQBN"),
        discovery_timeout: int = Field(5, description="Discovery timeout in seconds"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """Attach a board to a sketch for persistent association"""
        sketch_path = self.sketch_dir / sketch_name

        if not sketch_path.exists():
            return {"success": False, "error": f"Sketch '{sketch_name}' not found"}

        args = ["board", "attach", str(sketch_path)]

        # Need either port or FQBN
        if port:
            args.extend(["--port", port])
        elif fqbn:
            args.extend(["--fqbn", fqbn])
        else:
            return {"success": False, "error": "Either port or fqbn must be provided"}

        args.extend(["--discovery-timeout", f"{discovery_timeout}s"])

        result = await self._run_arduino_cli(args)

        if result["success"]:
            # Read sketch.json to verify attachment
            sketch_json_path = sketch_path / "sketch.json"
            attached_info = {}

            if sketch_json_path.exists():
                with open(sketch_json_path) as f:
                    sketch_data = json.load(f)
                    attached_info = {
                        "cpu": sketch_data.get("cpu"),
                        "port": sketch_data.get("port"),
                        "fqbn": sketch_data.get("cpu", {}).get("fqbn")
                    }

            return {
                "success": True,
                "sketch": sketch_name,
                "attached": attached_info,
                "message": f"Board attached to sketch '{sketch_name}'"
            }

        return result

    @mcp_tool(
        name="arduino_board_search_online",
        description="Search for boards in the online index (not yet installed)"
    )
    async def search_boards_online(
        self,
        query: str = Field(..., description="Search query for boards"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """Search for boards in the online package index"""
        args = ["board", "search", query]

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        data = result.get("data", {})
        boards = data.get("boards", [])

        # Process search results
        results = []
        for board in boards:
            board_info = {
                "name": board.get("name"),
                "platform": board.get("platform", {}).get("id"),
                "package": board.get("platform", {}).get("maintainer"),
                "website": board.get("platform", {}).get("website"),
                "email": board.get("platform", {}).get("email"),
                "installed": board.get("platform", {}).get("installed") is not None,
                "latest_version": board.get("platform", {}).get("latest_version"),
                "install_command": f"arduino_install_core('{board.get('platform', {}).get('id')}')"
            }
            results.append(board_info)

        # Group by installation status
        installed = [b for b in results if b["installed"]]
        available = [b for b in results if not b["installed"]]

        return {
            "success": True,
            "query": query,
            "total_results": len(results),
            "installed_count": len(installed),
            "available_count": len(available),
            "installed_boards": installed,
            "available_boards": available
        }

    @mcp_tool(
        name="arduino_board_identify",
        description="Auto-detect board type from connected port"
    )
    async def identify_board(
        self,
        port: str = Field(..., description="Port to identify board on"),
        timeout: int = Field(10, description="Timeout in seconds"),
        ctx: Context = None
    ) -> dict[str, Any]:
        """Identify board connected to a specific port"""
        # Arduino CLI board list doesn't filter by port, it lists all ports
        # We'll get all boards and filter for the requested port
        args = ["board", "list", "--discovery-timeout", f"{timeout}s"]

        result = await self._run_arduino_cli(args)

        if not result["success"]:
            return result

        data = result.get("data", {})

        # Handle case where data is not a list (could be empty or string)
        if not isinstance(data, list):
            data = []

        # Find the port in the results
        for detected_port in data:
            if detected_port.get("port", {}).get("address") == port:
                port_info = detected_port.get("port", {})
                boards = detected_port.get("matching_boards", [])

                if boards:
                    # Found matching board
                    board = boards[0]  # Take first match
                    return {
                        "success": True,
                        "port": port,
                        "identified": True,
                        "board": {
                            "name": board.get("name"),
                            "fqbn": board.get("fqbn"),
                            "platform": board.get("platform")
                        },
                        "port_details": {
                            "protocol": port_info.get("protocol"),
                            "protocol_label": port_info.get("protocol_label"),
                            "properties": port_info.get("properties", {})
                        },
                        "confidence": "high" if len(boards) == 1 else "medium",
                        "alternative_boards": boards[1:] if len(boards) > 1 else []
                    }
                else:
                    # Port found but no board identified
                    return {
                        "success": True,
                        "port": port,
                        "identified": False,
                        "port_details": {
                            "protocol": port_info.get("protocol"),
                            "protocol_label": port_info.get("protocol_label"),
                            "properties": port_info.get("properties", {})
                        },
                        "message": "Port found but board type could not be identified",
                        "suggestion": "Try manual board selection or install additional cores"
                    }

        return {
            "success": False,
            "error": f"No device found on port {port}",
            "suggestion": "Check connection and port permissions"
        }
