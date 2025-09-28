"""WireViz circuit diagram generation component"""
import datetime
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_resource, mcp_tool
from fastmcp.utilities.types import Image
from mcp.types import SamplingMessage, ToolAnnotations
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class WireVizRequest(BaseModel):
    """Request model for WireViz operations"""
    yaml_content: str | None = Field(None, description="WireViz YAML content")
    description: str | None = Field(None, description="Natural language circuit description")
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
    ) -> dict[str, Any]:
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
                from mcp.types import TextContent
                return TextContent(
                    type="text",
                    text=f"Error: {error_msg}"
                )

            # Find generated PNG
            png_files = list(output_dir.glob("*.png"))
            if not png_files:
                from mcp.types import TextContent
                return TextContent(
                    type="text",
                    text="Error: No PNG file generated"
                )

            png_path = png_files[0]

            # Read image data
            with open(png_path, "rb") as f:
                image_data = f.read()

            # Open image in default viewer
            self._open_file(png_path)

            # Return the Image directly so FastMCP converts it to ImageContent
            # Include path information in the image annotations
            return Image(
                data=image_data,  # Use raw bytes, not encoded
                format="png",
                annotations={
                    "description": f"Circuit diagram generated: {png_path}",
                    "paths": {
                        "yaml": str(yaml_path),
                        "png": str(png_path),
                        "directory": str(output_dir)
                    }
                }
            )

        except subprocess.TimeoutExpired:
            from mcp.types import TextContent
            return TextContent(
                type="text",
                text=f"Error: WireViz timed out after {self.config.command_timeout} seconds"
            )
        except Exception as e:
            log.exception("WireViz generation failed")
            from mcp.types import TextContent
            return TextContent(
                type="text",
                text=f"Error: {str(e)}"
            )

    @mcp_tool(
        name="wireviz_generate_from_description",
        description="Generate circuit diagram from natural language description",
        annotations=ToolAnnotations(
            title="Generate Circuit from Description",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def generate_from_description(
        self,
        ctx: Context,
        description: str,
        sketch_name: str = "",
        output_base: str = "circuit"
    ) -> dict[str, Any]:
        """Generate circuit diagram from natural language description

        This method intelligently handles both sampling-capable and non-sampling clients:
        1. Always tries sampling first for clients that support it
        2. Falls back gracefully to template generation when sampling isn't available
        3. Provides helpful feedback about which mode was used

        Args:
            ctx: FastMCP context (automatically injected during requests)
            description: Natural language description of the circuit
            sketch_name: Optional Arduino sketch name for context
            output_base: Base name for output files
        """

        try:
            # Track which method we use for generation
            generation_method = "unknown"
            yaml_content = None

            # Always try sampling first if the context has the method
            if hasattr(ctx, 'sample') and callable(ctx.sample):
                try:
                    log.info("Attempting to use client sampling for WireViz generation")

                    # Create prompt for YAML generation
                    prompt = self._create_wireviz_prompt(description, sketch_name)

                    # Use client sampling to generate WireViz YAML
                    from mcp.types import TextContent
                    messages = [
                        SamplingMessage(
                            role="user",
                            content=TextContent(
                                type="text",
                                text=f"You are an expert at creating WireViz YAML circuit diagrams. Return ONLY valid YAML content, no explanations or markdown code blocks.\n\n{prompt}"
                            )
                        )
                    ]

                    # Request completion from the client
                    result = await ctx.sample(
                        messages=messages,
                        max_tokens=2000,
                        temperature=0.3
                    )

                    if result and result.content:
                        yaml_content = self._clean_yaml_content(result.content)
                        generation_method = "ai-generated"
                        log.info("Successfully generated WireViz YAML using client sampling")
                    else:
                        # Sampling returned empty result
                        log.info("Client sampling returned empty result, falling back to template")
                        yaml_content = self._generate_template_yaml(description)
                        generation_method = "template-with-sampling-context"

                except Exception as e:
                    # Sampling failed - this is expected for some clients like Claude Desktop
                    error_msg = str(e)
                    if "Method not found" in error_msg:
                        log.info("Client doesn't support sampling endpoint (expected for Claude Desktop)")
                    else:
                        log.warning(f"Sampling failed with unexpected error: {error_msg}")

                    yaml_content = self._generate_template_yaml(description)
                    generation_method = "template-fallback"

            else:
                # Context doesn't have sample method at all
                log.info("Context doesn't provide sampling capability, using template")
                yaml_content = self._generate_template_yaml(description)
                generation_method = "template-no-sampling"

            # Generate diagram from YAML (regardless of source)
            diagram_result = await self.generate_from_yaml(
                yaml_content=yaml_content,
                output_base=output_base
            )

            # If we get an Image result, enhance its annotations with generation method
            if hasattr(diagram_result, 'annotations') and isinstance(diagram_result.annotations, dict):
                diagram_result.annotations['generation_method'] = generation_method
                if generation_method.startswith('template'):
                    diagram_result.annotations['note'] = (
                        "This is a template diagram. "
                        "For AI-generated diagrams, use a client that supports sampling "
                        "or customize the YAML manually."
                    )
                elif generation_method == 'ai-generated':
                    diagram_result.annotations['note'] = (
                        "AI-generated circuit diagram based on your description"
                    )

            return diagram_result

        except Exception as e:
            log.exception("WireViz generation failed completely")
            from mcp.types import TextContent
            return TextContent(
                type="text",
                text=f"Error: Generation failed: {str(e)}\n\nPlease check the logs for details."
            )

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

    def _generate_template_yaml(self, description: str) -> str:
        """Generate an intelligent template YAML based on keywords in the description

        This provides better starting points when AI sampling isn't available.
        """
        desc_lower = description.lower()

        # Detect common components and generate appropriate template
        # Check display first (before LED) to catch OLED/LCD properly
        if 'display' in desc_lower or 'lcd' in desc_lower or 'oled' in desc_lower:
            template = self._generate_display_template(description)
        elif 'led' in desc_lower:
            template = self._generate_led_template(description)
        elif 'motor' in desc_lower or 'servo' in desc_lower:
            template = self._generate_motor_template(description)
        elif 'sensor' in desc_lower:
            template = self._generate_sensor_template(description)
        elif 'button' in desc_lower or 'switch' in desc_lower:
            template = self._generate_button_template(description)
        else:
            # Generic template
            template = f"""# WireViz Circuit Diagram
# Generated from: {description[:100]}...
# Note: This is a template. Customize it for your specific circuit.
# For AI-generated diagrams, use a client that supports sampling.

connectors:
  Arduino:
    type: Arduino Uno
    subtype: female
    pinlabels: [GND, 5V, 3.3V, D2, D3, D4, D5, A0, A1]
    notes: Main microcontroller board

  Component1:
    type: Component
    subtype: female
    pinlabels: [Pin1, Pin2, Pin3]
    notes: Customize this for your component

cables:
  Cable1:
    wirecount: 3
    colors: [BK, RD, BL]  # Black, Red, Blue
    gauge: 22 AWG
    notes: Connection cable

connections:
  -
    - Arduino: [GND]
    - Cable1: [1]
    - Component1: [Pin1]
  -
    - Arduino: [5V]
    - Cable1: [2]
    - Component1: [Pin2]
  -
    - Arduino: [D2]
    - Cable1: [3]
    - Component1: [Pin3]

options:
  fontname: arial
  bgcolor: white
  color_mode: full
"""
        return template

    def _generate_led_template(self, description: str) -> str:
        """Generate LED circuit template"""
        return f"""# WireViz LED Circuit
# Description: {description[:100]}...
# Template for LED circuits - customize as needed

connectors:
  Arduino:
    type: Arduino Uno
    subtype: female
    pinlabels: [GND, 5V, D9, D10, D11]
    notes: Arduino board with PWM pins

  LED_Module:
    type: LED with Resistor
    subtype: female
    pinlabels: [Cathode(-), Anode(+)]
    notes: LED with current limiting resistor (220Ω)

cables:
  LED_Cable:
    wirecount: 2
    colors: [BK, RD]  # Black (GND), Red (Signal)
    gauge: 22 AWG
    notes: LED connection cable

connections:
  -
    - Arduino: [GND]
    - LED_Cable: [1]
    - LED_Module: [Cathode(-)]
  -
    - Arduino: [D9]
    - LED_Cable: [2]
    - LED_Module: [Anode(+)]

options:
  fontname: arial
  bgcolor: white
  color_mode: full
"""

    def _generate_motor_template(self, description: str) -> str:
        """Generate motor/servo circuit template"""
        return f"""# WireViz Motor/Servo Circuit
# Description: {description[:100]}...
# Template for motor control - customize as needed

connectors:
  Arduino:
    type: Arduino Uno
    subtype: female
    pinlabels: [GND, 5V, D9]
    notes: Arduino board

  Servo:
    type: Servo Motor
    subtype: female
    pinlabels: [GND, VCC, Signal]
    notes: Standard servo motor

cables:
  Servo_Cable:
    wirecount: 3
    colors: [BN, RD, OR]  # Brown (GND), Red (5V), Orange (Signal)
    gauge: 22 AWG
    notes: Servo connection cable

connections:
  -
    - Arduino: [GND]
    - Servo_Cable: [1]
    - Servo: [GND]
  -
    - Arduino: [5V]
    - Servo_Cable: [2]
    - Servo: [VCC]
  -
    - Arduino: [D9]
    - Servo_Cable: [3]
    - Servo: [Signal]

options:
  fontname: arial
  bgcolor: white
  color_mode: full
"""

    def _generate_sensor_template(self, description: str) -> str:
        """Generate sensor circuit template"""
        return f"""# WireViz Sensor Circuit
# Description: {description[:100]}...
# Template for sensor connections - customize as needed

connectors:
  Arduino:
    type: Arduino Uno
    subtype: female
    pinlabels: [GND, 5V, A0, A1]
    notes: Arduino board with analog inputs

  Sensor:
    type: Sensor Module
    subtype: female
    pinlabels: [GND, VCC, Signal, NC]
    notes: Generic sensor module

cables:
  Sensor_Cable:
    wirecount: 3
    colors: [BK, RD, YE]  # Black (GND), Red (5V), Yellow (Signal)
    gauge: 22 AWG
    notes: Sensor connection cable

connections:
  -
    - Arduino: [GND]
    - Sensor_Cable: [1]
    - Sensor: [GND]
  -
    - Arduino: [5V]
    - Sensor_Cable: [2]
    - Sensor: [VCC]
  -
    - Arduino: [A0]
    - Sensor_Cable: [3]
    - Sensor: [Signal]

options:
  fontname: arial
  bgcolor: white
  color_mode: full
"""

    def _generate_button_template(self, description: str) -> str:
        """Generate button/switch circuit template"""
        return f"""# WireViz Button/Switch Circuit
# Description: {description[:100]}...
# Template for button input - customize as needed

connectors:
  Arduino:
    type: Arduino Uno
    subtype: female
    pinlabels: [GND, 5V, D2]
    notes: Arduino board with digital input

  Button:
    type: Push Button
    subtype: female
    pinlabels: [Terminal1, Terminal2]
    notes: Momentary push button with pull-up resistor

cables:
  Button_Cable:
    wirecount: 2
    colors: [BK, GN]  # Black (GND), Green (Signal)
    gauge: 22 AWG
    notes: Button connection cable

connections:
  -
    - Arduino: [GND]
    - Button_Cable: [1]
    - Button: [Terminal1]
  -
    - Arduino: [D2]
    - Button_Cable: [2]
    - Button: [Terminal2]

options:
  fontname: arial
  bgcolor: white
  color_mode: full
  notes: Pull-up resistor (10kΩ) connects D2 to 5V
"""

    def _generate_display_template(self, description: str) -> str:
        """Generate display circuit template"""
        return f"""# WireViz Display Circuit
# Description: {description[:100]}...
# Template for display connections - customize as needed

connectors:
  Arduino:
    type: Arduino Uno
    subtype: female
    pinlabels: [GND, 5V, A4/SDA, A5/SCL]
    notes: Arduino with I2C pins

  Display:
    type: I2C Display
    subtype: female
    pinlabels: [GND, VCC, SDA, SCL]
    notes: I2C OLED/LCD Display

cables:
  I2C_Cable:
    wirecount: 4
    colors: [BK, RD, BL, YE]  # Black (GND), Red (5V), Blue (SDA), Yellow (SCL)
    gauge: 22 AWG
    notes: I2C connection cable

connections:
  -
    - Arduino: [GND]
    - I2C_Cable: [1]
    - Display: [GND]
  -
    - Arduino: [5V]
    - I2C_Cable: [2]
    - Display: [VCC]
  -
    - Arduino: [A4/SDA]
    - I2C_Cable: [3]
    - Display: [SDA]
  -
    - Arduino: [A5/SCL]
    - I2C_Cable: [4]
    - Display: [SCL]

options:
  fontname: arial
  bgcolor: white
  color_mode: full
  notes: I2C communication at 0x3C or 0x27 address
"""

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
