"""Configuration module for MCP Arduino Server"""
import os
from pathlib import Path
from typing import Optional, Set
from pydantic import BaseModel, Field


class ArduinoServerConfig(BaseModel):
    """Central configuration for Arduino MCP Server"""

    # Arduino CLI settings
    arduino_cli_path: str = Field(
        default="arduino-cli",
        description="Path to arduino-cli executable"
    )

    sketches_base_dir: Path = Field(
        default_factory=lambda: Path.home() / "Documents" / "Arduino_MCP_Sketches",
        description="Base directory for Arduino sketches"
    )

    @property
    def build_temp_dir(self) -> Path:
        """Build temp directory (derived from sketches_base_dir)"""
        return self.sketches_base_dir / "_build_temp"

    @property
    def sketch_dir(self) -> Path:
        """Alias for sketches_base_dir for component compatibility"""
        return self.sketches_base_dir

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

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist"""
        for dir_path in [
            self.sketches_base_dir,
            self.build_temp_dir,
            self.arduino_data_dir,
            self.arduino_user_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)