"""WireViz circuit diagram generation component"""
import base64
import datetime
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional, Any

from fastmcp import Context
from fastmcp.utilities.types import Image
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool, mcp_resource
from mcp.types import ToolAnnotations, SamplingMessage
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class WireVizRequest(BaseModel):
    """Request model for WireViz operations"""
    yaml_content: Optional[str] = Field(None, description="WireViz YAML content")
    description: Optional[str] = Field(None, description="Natural language circuit description")
    sketch_name: str = Field("circuit", description="Name for output files")
    output_base: str = Field("circuit", description="Base name for output files")


class WireViz(MCPMixin):
    """WireViz circuit diagram generation component"""

    def __init__(self, config):
        """Initialize WireViz mixin with configuration"""
        self.config = config
        self.wireviz_path = config.wireviz_path
        self.sketches_base_dir = config.sketches_base_dir

    @mcp_resource(uri="wireviz://instructions")
    async def get_wireviz_instructions(self) -> str:
        """WireViz usage instructions and examples"""
        return """
# WireViz Circuit Diagram Instructions

WireViz is a tool for generating circuit wiring diagrams from YAML descriptions.

## Basic YAML Structure:

```yaml
connectors:
  Arduino:
    type: Arduino Uno
    pins: [GND, 5V, D2, D3, A0]

  LED:
    type: LED
    pins: [cathode, anode]

cables:
  power:
    colors: [BK, RD]  # Black, Red
    gauge: 22 AWG

connections:
  - Arduino: [GND]
    cable: [1]
    LED: [cathode]
  - Arduino: [D2]
    cable: [2]
    LED: [anode]
```

## Color Codes:
- BK: Black, RD: Red, BL: Blue, GN: Green, YE: Yellow
- OR: Orange, VT: Violet, GY: Gray, WH: White, BN: Brown

## Tips:
1. Define all connectors first
2. Specify cable properties (colors, gauge)
3. Map connections clearly
4. Use descriptive names

For AI-powered generation from descriptions, use the
`wireviz_generate_from_description` tool.
"""

    @mcp_tool(
        name="wireviz_generate_from_yaml",
        description="Generate circuit diagram from WireViz YAML",
        annotations=ToolAnnotations(
            title="Generate Circuit Diagram from YAML",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def generate_from_yaml(
        self,
        yaml_content: str,
        output_base: str = "circuit"
    ) -> Dict[str, Any]:
        """Generate circuit diagram from WireViz YAML"""
        try:
            # Create timestamped output directory
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = self.sketches_base_dir / f"wireviz_{timestamp}"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Write YAML to temporary file
            yaml_path = output_dir / f"{output_base}.yaml"
            yaml_path.write_text(yaml_content)

            # Run WireViz
            cmd = [self.wireviz_path, str(yaml_path), "-o", str(output_dir)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout
            )

            if result.returncode != 0:
                error_msg = f"WireViz failed: {result.stderr}"
                log.error(error_msg)
                return {"error": error_msg}

            # Find generated PNG
            png_files = list(output_dir.glob("*.png"))
            if not png_files:
                return {"error": "No PNG file generated"}

            png_path = png_files[0]

            # Read and encode image
            with open(png_path, "rb") as f:
                image_data = f.read()
                encoded_image = base64.b64encode(image_data).decode("utf-8")

            # Open image in default viewer
            self._open_file(png_path)

            return {
                "success": True,
                "message": f"Circuit diagram generated: {png_path}",
                "image": Image(data=encoded_image, format="png"),
                "paths": {
                    "yaml": str(yaml_path),
                    "png": str(png_path),
                    "directory": str(output_dir)
                }
            }

        except subprocess.TimeoutExpired:
            return {"error": f"WireViz timed out after {self.config.command_timeout} seconds"}
        except Exception as e:
            log.exception("WireViz generation failed")
            return {"error": str(e)}

    @mcp_tool(
        name="wireviz_generate_from_description",
        description="Generate circuit diagram from natural language using client's LLM",
        annotations=ToolAnnotations(
            title="Generate Circuit from Description (AI)",
            destructiveHint=False,
            idempotentHint=False,
            requiresSampling=True,  # Indicates this tool needs sampling support
        )
    )
    async def generate_from_description(
        self,
        ctx: Context | None,  # Type as optional to support debugging/testing
        description: str,
        sketch_name: str = "",
        output_base: str = "circuit"
    ) -> Dict[str, Any]:
        """Generate circuit diagram from natural language description using client's LLM

        Args:
            ctx: FastMCP context (automatically injected during requests)
            description: Natural language description of the circuit
            sketch_name: Optional Arduino sketch name for context
            output_base: Base name for output files
        """

        # Check if context and sampling are available
        if ctx is None:
            return {
                "error": "No context available - this tool must be called through MCP",
                "hint": "Make sure you're using an MCP client that supports sampling"
            }

        if not hasattr(ctx, 'sample'):
            return {
                "error": "Client sampling not available",
                "hint": "Your MCP client must support sampling for AI-powered generation",
                "fallback": "You can still create diagrams by writing WireViz YAML manually"
            }

        try:
            # Create prompt for YAML generation
            prompt = self._create_wireviz_prompt(description, sketch_name)

            # Use client sampling to generate WireViz YAML
            from mcp.types import TextContent
            messages = [
                SamplingMessage(
                    role="user",
                    content=TextContent(type="text", text=f"You are an expert at creating WireViz YAML circuit diagrams. Return ONLY valid YAML content, no explanations or markdown code blocks.\n\n{prompt}")
                )
            ]

            # Request completion from the client
            result = await ctx.sample(
                messages=messages,
                max_tokens=2000,
                temperature=0.3,
                stop_sequences=["```"]
            )

            if not result or not result.content:
                return {"error": "No response from client LLM"}

            yaml_content = result.content

            # Clean up the YAML (remove markdown if present)
            yaml_content = self._clean_yaml_content(yaml_content)

            # Generate diagram from YAML
            diagram_result = await self.generate_from_yaml(
                yaml_content=yaml_content,
                output_base=output_base
            )

            if "error" not in diagram_result:
                diagram_result["yaml_generated"] = yaml_content
                diagram_result["generated_by"] = "client_llm_sampling"

            return diagram_result

        except Exception as e:
            log.exception("Client-based WireViz generation failed")
            return {"error": f"Generation failed: {str(e)}"}

    def _create_wireviz_prompt(self, description: str, sketch_name: str) -> str:
        """Create prompt for AI to generate WireViz YAML"""
        base_prompt = """Generate a WireViz YAML circuit diagram for the following description:

Description: {description}

Requirements:
1. Use proper WireViz YAML syntax
2. Include all necessary connectors, cables, and connections
3. Use appropriate wire colors and gauges
4. Add descriptive labels
5. Follow electrical safety standards

Return ONLY the YAML content, no explanations."""

        if sketch_name:
            base_prompt += f"\n\nThis is for an Arduino sketch named: {sketch_name}"

        return base_prompt.format(description=description)

    def _clean_yaml_content(self, content: str) -> str:
        """Remove markdown code blocks if present"""
        lines = content.strip().split('\n')

        # Remove markdown code fence if present
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines[-1].startswith('```'):
            lines = lines[:-1]

        return '\n'.join(lines)

    def _open_file(self, file_path: Path) -> None:
        """Open file in default system application"""
        # Skip file opening during tests
        if os.environ.get('TESTING_MODE') == '1':
            log.info(f"Skipping file opening for {file_path} (testing mode)")
            return

        try:
            if os.name == 'posix':  # macOS and Linux
                if os.uname().sysname == 'Darwin':
                    subprocess.run(['open', str(file_path)], check=False)
                else:
                    subprocess.run(['xdg-open', str(file_path)], check=False)
            elif os.name == 'nt':  # Windows
                subprocess.run(['cmd', '/c', 'start', '', str(file_path)], check=False, shell=True)
        except Exception as e:
            log.warning(f"Could not open file automatically: {e}")