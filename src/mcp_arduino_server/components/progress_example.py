"""
Example of how to add progress reporting to Arduino operations

This demonstrates the pattern for adding progress and logging to MCP tools.
"""

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from mcp.types import ToolAnnotations


class ProgressExample(MCPMixin):
    """Example component showing progress reporting patterns"""

    @mcp_tool(
        name="example_compile_with_progress",
        description="Example showing compilation with progress updates",
        annotations=ToolAnnotations(
            title="Compile with Progress",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def compile_with_progress(
        self,
        ctx: Context | None,
        sketch_name: str
    ) -> dict:
        """
        Example of compilation with detailed progress reporting.

        Progress stages:
        1. Initialization (0-10%)
        2. Parsing sketch (10-30%)
        3. Compiling core (30-60%)
        4. Linking (60-90%)
        5. Complete (90-100%)
        """

        # Stage 1: Initialization
        if ctx:
            await ctx.info(f"🚀 Starting compilation of '{sketch_name}'")
            await ctx.report_progress(5, 100)
            await ctx.debug("Checking sketch directory...")

        # Simulate checking
        # ... actual check code ...

        if ctx:
            await ctx.report_progress(10, 100)
            await ctx.debug("Sketch found, parsing...")

        # Stage 2: Parsing
        if ctx:
            await ctx.info("📝 Parsing sketch files...")
            await ctx.report_progress(20, 100)

        # Simulate parsing
        # ... actual parsing code ...

        if ctx:
            await ctx.report_progress(30, 100)
            await ctx.debug("Sketch parsed successfully")

        # Stage 3: Compiling
        if ctx:
            await ctx.info("🔧 Compiling source files...")
            await ctx.report_progress(45, 100)

        # During compilation, report incremental progress
        for i in range(3):
            if ctx:
                await ctx.debug(f"Compiling module {i+1}/3...")
                await ctx.report_progress(45 + (i * 5), 100)

        # Stage 4: Linking
        if ctx:
            await ctx.info("🔗 Linking objects...")
            await ctx.report_progress(70, 100)

        # Simulate linking
        # ... actual linking code ...

        if ctx:
            await ctx.report_progress(90, 100)
            await ctx.debug("Generating binary...")

        # Stage 5: Complete
        if ctx:
            await ctx.report_progress(100, 100)
            await ctx.info(f"✅ Compilation complete for '{sketch_name}'")

        return {
            "success": True,
            "message": f"Sketch '{sketch_name}' compiled successfully",
            "binary_size": "12,456 bytes",
            "memory_usage": "1,234 bytes RAM"
        }

    @mcp_tool(
        name="example_upload_with_progress",
        description="Example showing upload with progress updates",
        annotations=ToolAnnotations(
            title="Upload with Progress",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def upload_with_progress(
        self,
        ctx: Context | None,
        sketch_name: str,
        port: str
    ) -> dict:
        """
        Example of upload with progress based on bytes transferred.
        """

        total_bytes = 12456  # Example binary size

        if ctx:
            await ctx.info(f"📤 Starting upload to {port}")
            await ctx.report_progress(0, total_bytes)

        # Simulate upload with byte-level progress
        bytes_sent = 0
        chunk_size = 1024

        while bytes_sent < total_bytes:
            # Simulate sending a chunk
            bytes_sent = min(bytes_sent + chunk_size, total_bytes)

            if ctx:
                await ctx.report_progress(bytes_sent, total_bytes)

                # Log at key milestones
                percent = (bytes_sent / total_bytes) * 100
                if percent in [25, 50, 75]:
                    await ctx.debug(f"Upload {percent:.0f}% complete")

        if ctx:
            await ctx.info("✅ Upload complete, verifying...")
            await ctx.debug("Board reset successful")

        return {
            "success": True,
            "message": f"Uploaded '{sketch_name}' to {port}",
            "bytes_uploaded": total_bytes,
            "upload_speed": "115200 baud"
        }

    @mcp_tool(
        name="example_search_with_indeterminate",
        description="Example showing indeterminate progress for searches",
        annotations=ToolAnnotations(
            title="Search with Indeterminate Progress",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def search_with_indeterminate(
        self,
        ctx: Context | None,
        query: str
    ) -> dict:
        """
        Example of indeterminate progress (no total) for operations
        where we don't know the final count ahead of time.
        """

        if ctx:
            await ctx.info(f"🔍 Searching for '{query}'...")
            # No total specified = indeterminate progress
            await ctx.report_progress(0)

        results_found = 0

        # Simulate finding results over time
        for batch in range(3):
            # Find some results
            batch_results = 5 * (batch + 1)
            results_found += batch_results

            if ctx:
                # Report current count without total
                await ctx.report_progress(results_found)
                await ctx.debug(f"Found {batch_results} more results...")

        if ctx:
            await ctx.info(f"✅ Search complete: {results_found} results found")

        return {
            "success": True,
            "query": query,
            "count": results_found,
            "results": [f"Result {i+1}" for i in range(results_found)]
        }


# Key patterns demonstrated:
#
# 1. **Percentage Progress**: report_progress(current, 100) for 0-100%
# 2. **Absolute Progress**: report_progress(bytes_sent, total_bytes)
# 3. **Indeterminate Progress**: report_progress(count) with no total
# 4. **Log Levels**:
#    - ctx.debug() for detailed diagnostic info
#    - ctx.info() for key milestones and status
#    - ctx.warning() for potential issues
#    - ctx.error() for failures
# 5. **Progress Granularity**: Update at meaningful intervals, not too frequently
# 6. **User Feedback**: Combine progress with informative log messages