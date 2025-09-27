"""Enhanced configuration with MCP roots support for Arduino MCP Server"""
import os
from pathlib import Path
from typing import Optional, Set, List, Dict, Any
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class ArduinoServerConfigWithRoots(BaseModel):
    """Enhanced configuration that integrates with MCP client roots"""

    # Arduino CLI settings
    arduino_cli_path: str = Field(
        default="arduino-cli",
        description="Path to arduino-cli executable"
    )

    # Fallback directories (used when no roots are provided)
    default_sketches_dir: Path = Field(
        default_factory=lambda: Path.home() / "Documents" / "Arduino_MCP_Sketches",
        description="Default directory for Arduino sketches when no roots provided"
    )

    arduino_data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".arduino15",
        description="Arduino data directory"
    )

    arduino_user_dir: Path = Field(
        default_factory=lambda: Path.home() / "Documents" / "Arduino",
        description="Arduino user directory"
    )

    default_fqbn: str = Field(
        default="arduino:avr:uno",
        description="Default Fully Qualified Board Name"
    )

    # WireViz settings
    wireviz_path: str = Field(
        default="wireviz",
        description="Path to WireViz executable"
    )

    # Client sampling settings
    enable_client_sampling: bool = Field(
        default=True,
        description="Enable client-side LLM sampling for AI features"
    )

    # Security settings
    allowed_file_extensions: Set[str] = Field(
        default={".ino", ".cpp", ".c", ".h", ".hpp", ".yaml", ".yml", ".txt", ".md"},
        description="Allowed file extensions for operations"
    )

    max_file_size: int = Field(
        default=1024 * 1024,  # 1MB
        description="Maximum file size in bytes"
    )

    # Performance settings
    command_timeout: float = Field(
        default=30.0,
        description="Command execution timeout in seconds"
    )

    fuzzy_search_threshold: int = Field(
        default=75,
        description="Fuzzy search similarity threshold (0-100)"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    # MCP Roots support
    use_mcp_roots: bool = Field(
        default=True,
        description="Use MCP client-provided roots when available"
    )

    preferred_root_name: Optional[str] = Field(
        default=None,
        description="Preferred root name to use for sketches (e.g., 'arduino', 'projects')"
    )

    # Runtime properties (set when roots are available)
    _active_roots: Optional[List[Dict[str, Any]]] = None
    _selected_sketch_dir: Optional[Path] = None

    def select_sketch_directory(self, roots: Optional[List[Dict[str, Any]]] = None) -> Path:
        """
        Select the best directory for Arduino sketches based on MCP roots.

        Priority order:
        1. Root with name matching preferred_root_name
        2. Root with 'arduino' in the name (case-insensitive)
        3. Root with 'project' in the name (case-insensitive)
        4. First available root
        5. Default fallback directory
        """
        self._active_roots = roots

        if not self.use_mcp_roots or not roots:
            logger.info(f"No MCP roots available, using default: {self.default_sketches_dir}")
            self._selected_sketch_dir = self.default_sketches_dir
            return self.default_sketches_dir

        # Convert roots to Path objects
        root_paths = []
        for root in roots:
            try:
                root_path = {
                    'name': root.get('name', 'unnamed'),
                    'path': Path(root['uri'].replace('file://', '')),
                    'original': root
                }
                root_paths.append(root_path)
                logger.info(f"Found MCP root: {root_path['name']} -> {root_path['path']}")
            except Exception as e:
                logger.warning(f"Failed to parse root {root}: {e}")

        if not root_paths:
            logger.info("No valid MCP roots, using default directory")
            self._selected_sketch_dir = self.default_sketches_dir
            return self.default_sketches_dir

        selected = None

        # 1. Check for preferred root name
        if self.preferred_root_name:
            for rp in root_paths:
                if rp['name'].lower() == self.preferred_root_name.lower():
                    selected = rp
                    logger.info(f"Selected preferred root: {rp['name']}")
                    break

        # 2. Look for 'arduino' in name
        if not selected:
            for rp in root_paths:
                if 'arduino' in rp['name'].lower() or 'arduino' in str(rp['path']).lower():
                    selected = rp
                    logger.info(f"Selected Arduino-related root: {rp['name']}")
                    break

        # 3. Look for 'project' in name
        if not selected:
            for rp in root_paths:
                if 'project' in rp['name'].lower() or 'project' in str(rp['path']).lower():
                    selected = rp
                    logger.info(f"Selected project-related root: {rp['name']}")
                    break

        # 4. Use first available root
        if not selected and root_paths:
            selected = root_paths[0]
            logger.info(f"Selected first available root: {selected['name']}")

        if selected:
            # Create Arduino subdirectory within the root
            sketch_dir = selected['path'] / 'Arduino_Sketches'
            sketch_dir.mkdir(parents=True, exist_ok=True)
            self._selected_sketch_dir = sketch_dir
            logger.info(f"Using sketch directory: {sketch_dir}")
            return sketch_dir

        # 5. Fallback to default
        logger.info(f"Falling back to default directory: {self.default_sketches_dir}")
        self._selected_sketch_dir = self.default_sketches_dir
        return self.default_sketches_dir

    @property
    def sketches_base_dir(self) -> Path:
        """Get the active sketches directory (roots-aware)"""
        if self._selected_sketch_dir:
            return self._selected_sketch_dir
        return self.default_sketches_dir

    @property
    def sketch_dir(self) -> Path:
        """Alias for compatibility"""
        return self.sketches_base_dir

    @property
    def build_temp_dir(self) -> Path:
        """Build temp directory (derived from sketches_base_dir)"""
        return self.sketches_base_dir / "_build_temp"

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist"""
        for dir_path in [
            self.sketches_base_dir,
            self.build_temp_dir,
            self.arduino_data_dir,
            self.arduino_user_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def get_roots_info(self) -> str:
        """Get information about active MCP roots"""
        if not self._active_roots:
            return "No MCP roots configured"

        info = ["Active MCP Roots:"]
        for root in self._active_roots:
            name = root.get('name', 'unnamed')
            uri = root.get('uri', 'unknown')
            info.append(f"  - {name}: {uri}")

        if self._selected_sketch_dir:
            info.append(f"\nSelected sketch directory: {self._selected_sketch_dir}")

        return "\n".join(info)