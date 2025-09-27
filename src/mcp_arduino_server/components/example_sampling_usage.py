"""
Example of how to use FastMCP sampling with WireViz manager

This shows the pattern for integrating client-side LLM sampling
into MCP servers, eliminating the need for API keys.
"""

from fastmcp import FastMCP, Context
from .wireviz_manager import WireVizManager
from ..config import ArduinoServerConfig


# Create the FastMCP server
mcp = FastMCP(
    name="Arduino & WireViz Server",
    description="Arduino development with AI-powered circuit diagrams"
)


@mcp.tool()
async def generate_circuit_from_description(
    ctx: Context,
    description: str,
    sketch_name: str = "",
    output_base: str = "circuit"
) -> dict:
    """
    Generate a circuit diagram from natural language description.

    Uses the client's LLM (e.g., Claude) to convert the description
    to WireViz YAML, then generates the diagram.

    No API keys needed - the client handles the AI completion!
    """
    config = ArduinoServerConfig()

    # Pass the context to enable sampling
    wireviz = WireVizManager(config, mcp_context=ctx)

    result = await wireviz.generate_from_description(
        description=description,
        sketch_name=sketch_name,
        output_base=output_base
    )

    return result


@mcp.tool()
async def generate_circuit_from_yaml(
    yaml_content: str,
    output_base: str = "circuit"
) -> dict:
    """
    Generate a circuit diagram directly from WireViz YAML.

    This doesn't require client sampling - just processes the YAML.
    """
    config = ArduinoServerConfig()

    # No context needed for direct YAML processing
    wireviz = WireVizManager(config)

    result = await wireviz.generate_from_yaml(
        yaml_content=yaml_content,
        output_base=output_base
    )

    return result


# The key insight:
# - Tools that need AI use the Context parameter to access sampling
# - The client (Claude, etc.) does the LLM work
# - No API keys or external services needed
# - Falls back gracefully if client doesn't support sampling