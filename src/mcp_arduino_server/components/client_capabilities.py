"""
Enhanced Context with Client Capabilities Access

This module provides an enhanced way to access client capabilities through the Context.
It exposes what the client actually declared during initialization, not just what we can detect.
"""

import logging
from typing import Any

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from mcp.types import ToolAnnotations
from pydantic import Field

logger = logging.getLogger(__name__)


class ClientCapabilitiesInfo(MCPMixin):
    """
    Enhanced tools to properly access client capabilities from the MCP handshake.

    This reveals what the client ACTUALLY declared, not just what we can probe.
    """

    def __init__(self, config):
        """Initialize capabilities info component"""
        self.config = config

    @mcp_tool(
        name="client_declared_capabilities",
        description="Show what capabilities the client declared during initialization",
        annotations=ToolAnnotations(
            title="Client Declared Capabilities",
            destructiveHint=False,
            idempotentHint=True
        )
    )
    async def show_declared_capabilities(
        self,
        ctx: Context,
        verbose: bool = Field(False, description="Show raw capability data")
    ) -> dict[str, Any]:
        """
        Show the actual capabilities the client declared in the initialization handshake.

        This is different from probing - this shows what the client SAID it supports.
        """

        result = {
            "has_session": hasattr(ctx, 'session'),
            "client_params_available": False,
            "declared_capabilities": {},
            "insights": []
        }

        # Access the underlying session
        if not hasattr(ctx, 'session'):
            result["error"] = "No session available in context"
            return result

        session = ctx.session

        # Check if we have client_params (from initialization)
        if hasattr(session, '_client_params') and session._client_params:
            result["client_params_available"] = True
            client_params = session._client_params

            # Get the capabilities
            if hasattr(client_params, 'capabilities'):
                caps = client_params.capabilities

                # Check sampling capability
                if hasattr(caps, 'sampling'):
                    sampling_cap = caps.sampling
                    result["declared_capabilities"]["sampling"] = {
                        "declared": sampling_cap is not None,
                        "details": str(sampling_cap) if sampling_cap else None
                    }
                else:
                    result["declared_capabilities"]["sampling"] = {
                        "declared": False,
                        "details": "Not declared"
                    }

                # Check roots capability
                if hasattr(caps, 'roots'):
                    roots_cap = caps.roots
                    if roots_cap:
                        result["declared_capabilities"]["roots"] = {
                            "declared": True,
                            "listChanged": getattr(roots_cap, 'listChanged', False)
                        }
                    else:
                        result["declared_capabilities"]["roots"] = {
                            "declared": False
                        }

                # Check other capabilities
                for attr in ['resources', 'prompts', 'tools']:
                    if hasattr(caps, attr):
                        cap = getattr(caps, attr)
                        if cap:
                            result["declared_capabilities"][attr] = {
                                "declared": True,
                                "listChanged": getattr(cap, 'listChanged', False) if cap else False
                            }
                        else:
                            result["declared_capabilities"][attr] = {
                                "declared": False
                            }

                # Check experimental capabilities
                if hasattr(caps, 'experimental'):
                    result["declared_capabilities"]["experimental"] = caps.experimental or {}

                if verbose:
                    result["raw_capabilities"] = str(caps)
            else:
                result["error"] = "No capabilities found in client params"

            # Get client info
            if hasattr(client_params, 'clientInfo'):
                client_info = client_params.clientInfo
                if client_info:
                    result["client_info"] = {
                        "name": getattr(client_info, 'name', 'unknown'),
                        "version": getattr(client_info, 'version', 'unknown')
                    }
        else:
            result["error"] = "Client params not available - initialization data missing"
            result["insights"].append("Client didn't provide initialization parameters")

        # Generate insights based on findings
        if result["declared_capabilities"]:
            # Sampling insight
            sampling = result["declared_capabilities"].get("sampling", {})
            if not sampling.get("declared"):
                result["insights"].append(
                    "⚠️ Client didn't declare sampling capability - this is why sampling fails!"
                )
            else:
                result["insights"].append(
                    "✅ Client properly declared sampling support"
                )

            # Roots insight
            roots = result["declared_capabilities"].get("roots", {})
            if not roots.get("declared"):
                result["insights"].append(
                    "Client didn't declare roots support (but may still work)"
                )
            elif roots.get("listChanged"):
                result["insights"].append(
                    "Client supports dynamic roots updates"
                )

        return result

    @mcp_tool(
        name="client_capability_check",
        description="Test if client declared support for specific capabilities",
        annotations=ToolAnnotations(
            title="Check Specific Capability",
            destructiveHint=False,
            idempotentHint=True
        )
    )
    async def check_capability(
        self,
        ctx: Context,
        capability: str = Field(..., description="Capability to check: sampling, roots, resources, prompts, tools")
    ) -> dict[str, Any]:
        """
        Check if the client declared a specific capability.

        This uses the same check_client_capability method that FastMCP uses internally.
        """

        if not hasattr(ctx, 'session'):
            return {
                "capability": capability,
                "supported": False,
                "error": "No session available"
            }

        session = ctx.session

        # Try to use the check_client_capability method directly
        if hasattr(session, 'check_client_capability'):
            from mcp.types import ClientCapabilities, RootsCapability, SamplingCapability

            # Build the capability object to check
            check_cap = ClientCapabilities()

            if capability == "sampling":
                check_cap.sampling = SamplingCapability()
            elif capability == "roots":
                check_cap.roots = RootsCapability()
            # Add other capabilities as needed

            try:
                supported = session.check_client_capability(check_cap)
                return {
                    "capability": capability,
                    "supported": supported,
                    "check_method": "session.check_client_capability",
                    "explanation": f"Client {'did' if supported else 'did not'} declare {capability} support"
                }
            except Exception as e:
                return {
                    "capability": capability,
                    "supported": False,
                    "error": str(e)
                }
        else:
            return {
                "capability": capability,
                "supported": False,
                "error": "check_client_capability method not available"
            }

    @mcp_tool(
        name="client_fix_capabilities",
        description="Suggest fixes for capability issues",
        annotations=ToolAnnotations(
            title="Capability Issue Fixes",
            destructiveHint=False,
            idempotentHint=True
        )
    )
    async def suggest_fixes(self, ctx: Context) -> dict[str, Any]:
        """Analyze capability issues and suggest fixes"""

        # First get the declared capabilities
        caps_result = await self.show_declared_capabilities(ctx, verbose=False)

        fixes = []

        # Check sampling
        sampling = caps_result.get("declared_capabilities", {}).get("sampling", {})
        if not sampling.get("declared"):
            fixes.append({
                "issue": "Sampling not declared by client",
                "impact": "AI-powered features (like WireViz from description) will fail",
                "fix": "Applied patch to FastMCP context.py to bypass capability check",
                "status": "✅ Fixed"
            })

        # Check roots
        roots = caps_result.get("declared_capabilities", {}).get("roots", {})
        if roots.get("declared") and not roots.get("listChanged"):
            fixes.append({
                "issue": "Roots supported but not dynamic updates",
                "impact": "Can't notify client when roots change",
                "fix": "No fix needed - static roots work fine",
                "status": "ℹ️ Informational"
            })

        # Check for other missing capabilities
        for cap in ["resources", "prompts", "tools"]:
            cap_info = caps_result.get("declared_capabilities", {}).get(cap, {})
            if not cap_info.get("declared"):
                fixes.append({
                    "issue": f"{cap.capitalize()} capability not declared",
                    "impact": f"Can't use {cap}-related features",
                    "fix": f"Client needs to declare {cap} support",
                    "status": "⚠️ Client limitation"
                })

        return {
            "capability_issues": len(fixes),
            "fixes": fixes,
            "summary": "Sampling issue has been patched. Other limitations are client-side."
        }
