"""
Client Debug Tool for Arduino MCP Server

This component provides comprehensive debugging information about the connected MCP client,
including capabilities, features, and current state. Essential for troubleshooting and
understanding what features are available.
"""

import logging
from datetime import datetime
from typing import Any

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from mcp.types import ToolAnnotations
from pydantic import Field

logger = logging.getLogger(__name__)


class ClientDebugInfo(MCPMixin):
    """
    Debug tool that reveals everything about the connected MCP client.

    This component helps developers and users understand:
    - What capabilities the client supports
    - What features are available
    - Current connection state
    - Why certain features might not work
    """

    def __init__(self, config):
        """Initialize debug component"""
        self.config = config
        self.client_info = {
            "connection_time": datetime.now().isoformat(),
            "capabilities_detected": {},
            "runtime_features": {},
            "test_results": {}
        }

    def update_capability(self, name: str, value: Any):
        """Update a detected capability"""
        self.client_info["capabilities_detected"][name] = value
        logger.info(f"Client capability detected: {name} = {value}")

    @mcp_tool(
        name="client_debug_info",
        description="Show comprehensive debug information about the MCP client",
        annotations=ToolAnnotations(
            title="Client Debug Information",
            destructiveHint=False,
            idempotentHint=True
        )
    )
    async def debug_info(
        self,
        ctx: Context,
        verbose: bool = Field(False, description="Show detailed technical information")
    ) -> dict[str, Any]:
        """
        Get comprehensive debug information about the connected MCP client.

        This tool reveals:
        - Client capabilities (roots, tools, prompts, resources)
        - Feature support (sampling, notifications)
        - Current state (roots, connections)
        - Runtime behavior
        """

        # ============================================================
        # 1. Check Notification Support
        # ============================================================

        notification_support = {
            "tools.listChanged": False,
            "resources.listChanged": False,
            "prompts.listChanged": False,
            "roots.listChanged": False
        }

        # These would be set during server initialization based on client capabilities
        # For now, we'll detect what we can at runtime

        # ============================================================
        # 2. Check Sampling Support
        # ============================================================

        sampling_info = await self._check_sampling_support(ctx)

        # ============================================================
        # 3. Check Roots Support
        # ============================================================

        roots_info = await self._check_roots_support(ctx)

        # ============================================================
        # 4. Check Resources Support
        # ============================================================

        resources_info = await self._check_resources_support(ctx)

        # ============================================================
        # 5. Check Context Features
        # ============================================================

        context_features = self._analyze_context(ctx, verbose)

        # ============================================================
        # 6. Runtime Tests
        # ============================================================

        runtime_tests = await self._run_runtime_tests(ctx)

        # ============================================================
        # 7. Build Debug Report
        # ============================================================

        debug_report = {
            "client_info": {
                "connection_time": self.client_info["connection_time"],
                "session_duration": self._calculate_session_duration()
            },
            "capabilities": {
                "notifications": notification_support,
                "sampling": sampling_info,
                "roots": roots_info,
                "resources": resources_info
            },
            "context_analysis": context_features,
            "runtime_tests": runtime_tests,
            "recommendations": self._generate_recommendations(
                sampling_info,
                roots_info,
                notification_support
            ),
            "feature_matrix": self._create_feature_matrix(
                sampling_info,
                roots_info,
                resources_info,
                notification_support
            )
        }

        if verbose:
            debug_report["technical_details"] = {
                "context_type": str(type(ctx)),
                "context_dir": [attr for attr in dir(ctx) if not attr.startswith('_')],
                "context_methods": {
                    attr: callable(getattr(ctx, attr))
                    for attr in dir(ctx)
                    if not attr.startswith('_')
                },
                "raw_capabilities": self.client_info.get("capabilities_detected", {})
            }

        return debug_report

    async def _check_sampling_support(self, ctx: Context) -> dict[str, Any]:
        """Check if client supports sampling (AI completion)"""

        sampling_info = {
            "supported": False,
            "method_exists": False,
            "callable": False,
            "test_result": None,
            "error": None
        }

        # Check if method exists
        if hasattr(ctx, 'sample'):
            sampling_info["method_exists"] = True

            # Check if it's callable
            if callable(ctx.sample):
                sampling_info["callable"] = True
                sampling_info["supported"] = True

                # Try to get method signature if possible
                try:
                    import inspect
                    sig = inspect.signature(ctx.sample)
                    sampling_info["signature"] = str(sig)
                except:
                    pass

                # We could try a test sampling, but that might be expensive
                sampling_info["test_result"] = "Available (not tested to avoid cost)"
            else:
                sampling_info["error"] = "sample attribute exists but is not callable"
        else:
            sampling_info["error"] = "sample method not found in context"

        return sampling_info

    async def _check_roots_support(self, ctx: Context) -> dict[str, Any]:
        """Check roots support and current roots"""

        roots_info = {
            "supported": False,
            "method_exists": False,
            "current_roots": [],
            "root_count": 0,
            "error": None
        }

        # Check if list_roots exists
        if hasattr(ctx, 'list_roots'):
            roots_info["method_exists"] = True

            # Try to get current roots
            try:
                roots = await ctx.list_roots()
                roots_info["supported"] = True
                roots_info["root_count"] = len(roots) if roots else 0

                # Parse roots information
                if roots:
                    for root in roots:
                        root_data = {
                            "name": getattr(root, 'name', 'unknown'),
                            "uri": getattr(root, 'uri', 'unknown')
                        }

                        # Parse URI to get path
                        if root_data["uri"].startswith("file://"):
                            root_data["path"] = root_data["uri"].replace("file://", "")

                        roots_info["current_roots"].append(root_data)

            except Exception as e:
                roots_info["error"] = f"Could not retrieve roots: {str(e)}"
        else:
            roots_info["error"] = "list_roots method not found in context"

        return roots_info

    async def _check_resources_support(self, ctx: Context) -> dict[str, Any]:
        """Check resources support"""

        resources_info = {
            "supported": False,
            "method_exists": False,
            "resource_count": 0,
            "templates_count": 0,
            "error": None
        }

        # Check for list_resources
        if hasattr(ctx, 'list_resources'):
            resources_info["method_exists"] = True

            try:
                # Some servers might expose resources
                resources = await ctx.list_resources()
                resources_info["supported"] = True
                resources_info["resource_count"] = len(resources) if resources else 0
            except:
                pass

        # Check for list_resource_templates
        if hasattr(ctx, 'list_resource_templates'):
            try:
                templates = await ctx.list_resource_templates()
                resources_info["templates_count"] = len(templates) if templates else 0
            except:
                pass

        return resources_info

    def _analyze_context(self, ctx: Context, verbose: bool) -> dict[str, Any]:
        """Analyze the context object"""

        context_info = {
            "available_methods": [],
            "available_properties": [],
            "mcp_specific": []
        }

        # Categorize context attributes
        for attr in dir(ctx):
            if attr.startswith('_'):
                continue

            attr_value = getattr(ctx, attr, None)

            if callable(attr_value):
                context_info["available_methods"].append(attr)

                # Identify MCP-specific methods
                if any(keyword in attr for keyword in ['resource', 'prompt', 'tool', 'sample', 'root']):
                    context_info["mcp_specific"].append(attr)
            else:
                context_info["available_properties"].append(attr)

        return context_info

    async def _run_runtime_tests(self, ctx: Context) -> dict[str, Any]:
        """Run runtime tests to verify features"""

        tests = {
            "roots_retrieval": "not_tested",
            "sampling_available": "not_tested",
            "context_type": str(type(ctx).__name__)
        }

        # Test roots retrieval
        try:
            if hasattr(ctx, 'list_roots'):
                roots = await ctx.list_roots()
                tests["roots_retrieval"] = "success" if roots is not None else "empty"
        except Exception as e:
            tests["roots_retrieval"] = f"failed: {str(e)[:50]}"

        # Test sampling (without actually calling it to avoid costs)
        if hasattr(ctx, 'sample') and callable(ctx.sample):
            tests["sampling_available"] = "available"
        else:
            tests["sampling_available"] = "not_available"

        return tests

    def _calculate_session_duration(self) -> str:
        """Calculate how long the session has been active"""

        try:
            start = datetime.fromisoformat(self.client_info["connection_time"])
            duration = datetime.now() - start

            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            seconds = duration.seconds % 60

            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        except:
            return "unknown"

    def _generate_recommendations(
        self,
        sampling_info: dict,
        roots_info: dict,
        notification_support: dict
    ) -> list[str]:
        """Generate recommendations based on client capabilities"""

        recommendations = []

        # Sampling recommendations
        if not sampling_info.get("supported"):
            recommendations.append(
                "🔸 Sampling not available - AI features will use fallback templates"
            )
        else:
            recommendations.append(
                "✅ Sampling available - AI-powered features fully functional"
            )

        # Roots recommendations
        if roots_info.get("root_count", 0) > 0:
            recommendations.append(
                f"✅ {roots_info['root_count']} root(s) configured - using client workspace"
            )
        elif roots_info.get("supported"):
            recommendations.append(
                "🔸 Roots supported but none configured - using default directories"
            )
        else:
            recommendations.append(
                "🔸 Roots not supported - using default directories"
            )

        # Notification recommendations
        if not any(notification_support.values()):
            recommendations.append(
                "🔸 No dynamic notifications - tools remain static during session"
            )

        return recommendations

    def _create_feature_matrix(
        self,
        sampling_info: dict,
        roots_info: dict,
        resources_info: dict,
        notification_support: dict
    ) -> dict[str, str]:
        """Create a feature support matrix"""

        def status_icon(supported: bool) -> str:
            return "✅" if supported else "❌"

        return {
            "AI Completion (sampling)": status_icon(sampling_info.get("supported", False)),
            "Workspace Roots": status_icon(roots_info.get("supported", False)),
            "Resources": status_icon(resources_info.get("supported", False)),
            "Dynamic Tools": status_icon(notification_support.get("tools.listChanged", False)),
            "Dynamic Resources": status_icon(notification_support.get("resources.listChanged", False)),
            "Dynamic Prompts": status_icon(notification_support.get("prompts.listChanged", False)),
            "Dynamic Roots": status_icon(notification_support.get("roots.listChanged", False))
        }


    @mcp_tool(
        name="client_test_sampling",
        description="Test if client sampling works with a simple prompt",
        annotations=ToolAnnotations(
            title="Test Client Sampling",
            destructiveHint=False,
            idempotentHint=True
        )
    )
    async def test_sampling(
        self,
        ctx: Context,
        test_prompt: str = Field("Say 'Hello MCP' in exactly 3 words", description="Simple test prompt")
    ) -> dict[str, Any]:
        """Test client sampling with a simple, low-cost prompt"""

        if not hasattr(ctx, 'sample'):
            return {
                "success": False,
                "error": "Sampling not available - ctx.sample method not found"
            }

        if not callable(ctx.sample):
            return {
                "success": False,
                "error": "ctx.sample exists but is not callable"
            }

        try:
            from mcp.types import SamplingMessage, TextContent

            messages = [
                SamplingMessage(
                    role="user",
                    content=TextContent(type="text", text=test_prompt)
                )
            ]

            # Try minimal sampling call
            result = await ctx.sample(
                messages=messages,
                max_tokens=20  # Very small to minimize cost
            )

            return {
                "success": True,
                "test_prompt": test_prompt,
                "response": result.content if result else "No response",
                "response_type": type(result).__name__ if result else "None",
                "sampling_works": True
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "sampling_works": False,
                "hint": "Check if the client has sampling configured correctly"
            }
