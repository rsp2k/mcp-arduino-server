"""Arduino Sketch management component"""
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool, mcp_resource
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)


class SketchRequest(BaseModel):
    """Request model for sketch operations"""
    sketch_name: str = Field(..., description="Name of the Arduino sketch")

    @field_validator('sketch_name')
    @classmethod
    def validate_sketch_name(cls, v):
        """Ensure sketch name is valid"""
        if not v or any(c in v for c in ['/', '\\', '..', '.']):
            raise ValueError("Invalid sketch name - cannot contain path separators or dots")
        return v


class ArduinoSketch(MCPMixin):
    """Arduino sketch management component"""

    def __init__(self, config):
        """Initialize Arduino sketch mixin with configuration"""
        self.config = config
        self.sketches_base_dir = config.sketches_base_dir
        self.build_temp_dir = config.build_temp_dir or (config.sketches_base_dir / "_build_temp")
        self.arduino_cli_path = config.arduino_cli_path
        self.default_fqbn = config.default_fqbn

    @mcp_resource(uri="arduino://sketches")
    async def list_sketches_resource(self) -> str:
        """List all Arduino sketches as a resource"""
        sketches = await self.list_sketches()
        return sketches

    @mcp_tool(
        name="arduino_create_sketch",
        description="Create a new Arduino sketch with boilerplate code",
        annotations=ToolAnnotations(
            title="Create Arduino Sketch",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def create_sketch(
        self,
        ctx: Context | None,
        sketch_name: str
    ) -> Dict[str, Any]:
        """Create a new Arduino sketch directory and .ino file with boilerplate code"""

        try:
            # Validate sketch name
            request = SketchRequest(sketch_name=sketch_name)

            # Create sketch directory
            sketch_dir = self.sketches_base_dir / request.sketch_name
            if sketch_dir.exists():
                return {
                    "error": f"Sketch '{request.sketch_name}' already exists",
                    "path": str(sketch_dir)
                }

            sketch_dir.mkdir(parents=True, exist_ok=True)

            # Create .ino file with boilerplate
            ino_file = sketch_dir / f"{request.sketch_name}.ino"
            boilerplate = f"""// {request.sketch_name}
// Created with MCP Arduino Server

void setup() {{
  // Initialize serial communication
  Serial.begin(9600);

  // Setup code here - runs once
  Serial.println("{request.sketch_name} initialized!");
}}

void loop() {{
  // Main code here - runs repeatedly

}}
"""
            ino_file.write_text(boilerplate)

            # Try to open in default editor
            self._open_file(ino_file)

            log.info(f"Created sketch: {sketch_dir}")

            return {
                "success": True,
                "message": f"Sketch '{request.sketch_name}' created successfully",
                "path": str(sketch_dir),
                "ino_file": str(ino_file)
            }

        except Exception as e:
            log.exception(f"Failed to create sketch: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_list_sketches",
        description="List all Arduino sketches in the sketches directory",
        annotations=ToolAnnotations(
            title="List Arduino Sketches",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def list_sketches(
        self,
        ctx: Context | None = None
    ) -> str:
        """List all valid Arduino sketches"""

        try:
            sketches = []

            if not self.sketches_base_dir.exists():
                return "No sketches directory found. Create your first sketch!"

            # Find all directories containing .ino files
            for item in self.sketches_base_dir.iterdir():
                if item.is_dir() and not item.name.startswith('_'):
                    # Check for .ino file with matching name
                    ino_file = item / f"{item.name}.ino"
                    if ino_file.exists():
                        sketches.append({
                            "name": item.name,
                            "path": str(item),
                            "ino_file": str(ino_file),
                            "size": ino_file.stat().st_size,
                            "modified": ino_file.stat().st_mtime
                        })

            if not sketches:
                return "No Arduino sketches found. Create one with 'arduino_create_sketch'!"

            # Format output
            output = f"Found {len(sketches)} Arduino sketch(es):\n\n"
            for sketch in sorted(sketches, key=lambda x: x['name']):
                output += f"📁 {sketch['name']}\n"
                output += f"   Path: {sketch['path']}\n"
                output += f"   Size: {sketch['size']} bytes\n\n"

            return output

        except Exception as e:
            log.exception(f"Failed to list sketches: {e}")
            return f"Error listing sketches: {str(e)}"

    @mcp_tool(
        name="arduino_compile_sketch",
        description="Compile an Arduino sketch without uploading",
        annotations=ToolAnnotations(
            title="Compile Arduino Sketch",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def compile_sketch(
        self,
        ctx: Context | None,
        sketch_name: str,
        board_fqbn: str = ""
    ) -> Dict[str, Any]:
        """Compile an Arduino sketch to verify code correctness"""

        try:
            # Validate sketch
            sketch_dir = self.sketches_base_dir / sketch_name
            if not sketch_dir.exists():
                return {"error": f"Sketch '{sketch_name}' not found"}

            ino_file = sketch_dir / f"{sketch_name}.ino"
            if not ino_file.exists():
                return {"error": f"No .ino file found for sketch '{sketch_name}'"}

            # Use provided FQBN or default
            fqbn = board_fqbn or self.default_fqbn

            # Prepare compile command
            cmd = [
                self.arduino_cli_path,
                "compile",
                "--fqbn", fqbn,
                "--build-path", str(self.build_temp_dir / sketch_name),
                str(sketch_dir)
            ]

            log.info(f"Compiling sketch: {' '.join(cmd)}")

            # Run compilation
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Sketch '{sketch_name}' compiled successfully",
                    "board": fqbn,
                    "output": result.stdout
                }
            else:
                return {
                    "error": "Compilation failed",
                    "board": fqbn,
                    "stderr": result.stderr,
                    "stdout": result.stdout
                }

        except subprocess.TimeoutExpired:
            return {"error": f"Compilation timed out after {self.config.command_timeout} seconds"}
        except Exception as e:
            log.exception(f"Failed to compile sketch: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_upload_sketch",
        description="Compile and upload sketch to connected Arduino board",
        annotations=ToolAnnotations(
            title="Upload Arduino Sketch",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def upload_sketch(
        self,
        ctx: Context | None,
        sketch_name: str,
        port: str,
        board_fqbn: str = ""
    ) -> Dict[str, Any]:
        """Compile and upload sketch to Arduino board"""

        try:
            # Validate sketch
            sketch_dir = self.sketches_base_dir / sketch_name
            if not sketch_dir.exists():
                return {"error": f"Sketch '{sketch_name}' not found"}

            # Use provided FQBN or default
            fqbn = board_fqbn or self.default_fqbn

            # Prepare upload command
            cmd = [
                self.arduino_cli_path,
                "upload",
                "--fqbn", fqbn,
                "--port", port,
                "--build-path", str(self.build_temp_dir / sketch_name),
                str(sketch_dir)
            ]

            log.info(f"Uploading sketch: {' '.join(cmd)}")

            # Run upload
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout * 2  # Upload takes longer
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Sketch '{sketch_name}' uploaded successfully",
                    "board": fqbn,
                    "port": port,
                    "output": result.stdout
                }
            else:
                return {
                    "error": "Upload failed",
                    "board": fqbn,
                    "port": port,
                    "stderr": result.stderr,
                    "stdout": result.stdout
                }

        except subprocess.TimeoutExpired:
            return {"error": f"Upload timed out after {self.config.command_timeout * 2} seconds"}
        except Exception as e:
            log.exception(f"Failed to upload sketch: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_read_sketch",
        description="Read the contents of an Arduino sketch file",
        annotations=ToolAnnotations(
            title="Read Arduino Sketch",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def read_sketch(
        self,
        ctx: Context | None,
        sketch_name: str,
        file_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Read the contents of a sketch file"""

        try:
            sketch_dir = self.sketches_base_dir / sketch_name
            if not sketch_dir.exists():
                return {"error": f"Sketch '{sketch_name}' not found"}

            # Determine which file to read
            if file_name:
                file_path = sketch_dir / file_name
            else:
                file_path = sketch_dir / f"{sketch_name}.ino"

            if not file_path.exists():
                return {"error": f"File '{file_path}' not found"}

            # Check file extension
            if file_path.suffix not in self.config.allowed_file_extensions:
                return {"error": f"File type '{file_path.suffix}' not allowed"}

            # Read file content
            content = file_path.read_text()

            return {
                "success": True,
                "path": str(file_path),
                "content": content,
                "size": len(content),
                "lines": len(content.splitlines())
            }

        except Exception as e:
            log.exception(f"Failed to read sketch: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_write_sketch",
        description="Write or update an Arduino sketch file",
        annotations=ToolAnnotations(
            title="Write Arduino Sketch",
            destructiveHint=True,
            idempotentHint=False,
        )
    )
    async def write_sketch(
        self,
        ctx: Context | None,
        sketch_name: str,
        content: str,
        file_name: Optional[str] = None,
        auto_compile: bool = True
    ) -> Dict[str, Any]:
        """Write or update a sketch file"""

        try:
            sketch_dir = self.sketches_base_dir / sketch_name

            # Create directory if it doesn't exist
            sketch_dir.mkdir(parents=True, exist_ok=True)

            # Determine target file
            if file_name:
                file_path = sketch_dir / file_name
            else:
                file_path = sketch_dir / f"{sketch_name}.ino"

            # Check file extension
            if file_path.suffix not in self.config.allowed_file_extensions:
                return {"error": f"File type '{file_path.suffix}' not allowed"}

            # Write content
            file_path.write_text(content)

            result = {
                "success": True,
                "message": f"File written successfully",
                "path": str(file_path),
                "size": len(content),
                "lines": len(content.splitlines())
            }

            # Auto-compile if requested and it's an .ino file
            if auto_compile and file_path.suffix == ".ino":
                compile_result = await self.compile_sketch(ctx, sketch_name)
                result["compilation"] = compile_result

            return result

        except Exception as e:
            log.exception(f"Failed to write sketch: {e}")
            return {"error": str(e)}

    def _open_file(self, file_path: Path) -> None:
        """Open file in default system application"""
        # Skip file opening during tests
        if os.environ.get('TESTING_MODE') == '1':
            log.info(f"Skipping file opening for {file_path} (testing mode)")
            return

        try:
            if os.name == 'posix':  # macOS and Linux
                subprocess.run(['open' if os.uname().sysname == 'Darwin' else 'xdg-open', str(file_path)])
            elif os.name == 'nt':  # Windows
                os.startfile(str(file_path))
        except Exception as e:
            log.warning(f"Could not open file automatically: {e}")