"""Arduino Debug component using PyArduinoDebug for GDB-like debugging"""
import asyncio
import json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool, mcp_resource
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class DebugCommand(str, Enum):
    """Available debug commands"""
    BREAK = "break"
    RUN = "run"
    CONTINUE = "continue"
    STEP = "step"
    NEXT = "next"
    PRINT = "print"
    BACKTRACE = "backtrace"
    INFO = "info"
    DELETE = "delete"
    QUIT = "quit"


class BreakpointRequest(BaseModel):
    """Request model for setting breakpoints"""
    location: str = Field(..., description="Function name or line number (file:line)")
    condition: Optional[str] = Field(None, description="Conditional expression for breakpoint")
    temporary: bool = Field(False, description="Whether breakpoint is temporary (deleted after hit)")


class ArduinoDebug(MCPMixin):
    """Arduino debugging component using PyArduinoDebug"""

    def __init__(self, config):
        """Initialize Arduino debug component with configuration"""
        self.config = config
        self.arduino_cli_path = config.arduino_cli_path
        self.sketches_base_dir = config.sketches_base_dir

        # Check for PyArduinoDebug availability
        self.pyadebug_path = shutil.which("arduino-dbg")
        if not self.pyadebug_path:
            log.warning("PyArduinoDebug not found. Install with: pip install PyArduinoDebug")

        # Active debug sessions
        self.debug_sessions = {}

    @mcp_resource(uri="arduino://debug/sessions")
    async def list_debug_sessions(self) -> str:
        """List all active debug sessions"""
        if not self.debug_sessions:
            return "No active debug sessions. Start one with 'arduino_debug_start'."

        output = f"Active Debug Sessions ({len(self.debug_sessions)}):\n\n"
        for session_id, session in self.debug_sessions.items():
            output += f"🐛 Session: {session_id}\n"
            output += f"   Sketch: {session['sketch']}\n"
            output += f"   Port: {session['port']}\n"
            output += f"   Status: {session['status']}\n"
            if session.get('breakpoints'):
                output += f"   Breakpoints: {len(session['breakpoints'])}\n"
            output += "\n"

        return output

    @mcp_tool(
        name="arduino_debug_start",
        description="Start a debugging session for an Arduino sketch",
        annotations=ToolAnnotations(
            title="Start Debug Session",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def debug_start(
        self,
        ctx: Context | None,
        sketch_name: str,
        port: str,
        board_fqbn: str = "",
        gdb_port: int = 4242
    ) -> Dict[str, Any]:
        """Start a debugging session for an Arduino sketch

        Args:
            sketch_name: Name of the sketch to debug
            port: Serial port of the Arduino
            board_fqbn: Board FQBN (e.g., arduino:avr:uno)
            gdb_port: Port for GDB server (default: 4242)
        """

        try:
            if not self.pyadebug_path:
                return {"error": "PyArduinoDebug not installed. Install with: pip install PyArduinoDebug"}

            # Validate sketch exists
            sketch_dir = self.sketches_base_dir / sketch_name
            if not sketch_dir.exists():
                return {"error": f"Sketch '{sketch_name}' not found"}

            # Generate session ID
            session_id = f"{sketch_name}_{port.replace('/', '_')}"

            if session_id in self.debug_sessions:
                return {"error": f"Debug session already active for {sketch_name} on {port}"}

            if ctx:
                await ctx.info(f"🚀 Starting debug session for '{sketch_name}'")
                await ctx.report_progress(10, 100)

            # First compile with debug symbols
            if ctx:
                await ctx.info("📝 Compiling sketch with debug symbols...")
                await ctx.report_progress(20, 100)

            fqbn = board_fqbn or self.config.default_fqbn
            compile_cmd = [
                self.arduino_cli_path,
                "compile",
                "--fqbn", fqbn,
                "--build-property", "compiler.optimization_flags=-Og -g",
                "--build-path", str(self.config.build_temp_dir / f"{sketch_name}_debug"),
                str(sketch_dir)
            ]

            compile_result = await asyncio.create_subprocess_exec(
                *compile_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await compile_result.communicate()

            if compile_result.returncode != 0:
                if ctx:
                    await ctx.error("❌ Compilation failed")
                return {
                    "error": "Compilation with debug symbols failed",
                    "stderr": stderr.decode()
                }

            if ctx:
                await ctx.report_progress(40, 100)
                await ctx.info("📤 Uploading debug build...")

            # Upload the debug build
            upload_cmd = [
                self.arduino_cli_path,
                "upload",
                "--fqbn", fqbn,
                "--port", port,
                "--build-path", str(self.config.build_temp_dir / f"{sketch_name}_debug"),
                str(sketch_dir)
            ]

            upload_result = await asyncio.create_subprocess_exec(
                *upload_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await upload_result.communicate()

            if upload_result.returncode != 0:
                if ctx:
                    await ctx.error("❌ Upload failed")
                return {
                    "error": "Debug build upload failed",
                    "stderr": stderr.decode()
                }

            if ctx:
                await ctx.report_progress(60, 100)
                await ctx.info(f"🔗 Starting GDB server on port {gdb_port}...")

            # Start PyArduinoDebug GDB server
            gdb_cmd = [
                self.pyadebug_path,
                "--port", port,
                "--gdb-port", str(gdb_port),
                "--elf", str(self.config.build_temp_dir / f"{sketch_name}_debug" / f"{sketch_name}.ino.elf")
            ]

            # Start GDB server as subprocess
            process = await asyncio.create_subprocess_exec(
                *gdb_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE
            )

            if ctx:
                await ctx.report_progress(80, 100)

            # Store session info
            self.debug_sessions[session_id] = {
                "sketch": sketch_name,
                "port": port,
                "fqbn": fqbn,
                "gdb_port": gdb_port,
                "process": process,
                "status": "running",
                "breakpoints": [],
                "variables": {}
            }

            if ctx:
                await ctx.report_progress(100, 100)
                await ctx.info(f"✅ Debug session started for '{sketch_name}' on {port}")
                await ctx.debug(f"GDB server listening on port {gdb_port}")

            return {
                "success": True,
                "session_id": session_id,
                "message": f"Debug session started for '{sketch_name}'",
                "gdb_port": gdb_port,
                "hint": "Use 'arduino_debug_break' to set breakpoints"
            }

        except Exception as e:
            log.exception(f"Failed to start debug session: {e}")
            if ctx:
                await ctx.error(f"Debug start failed: {str(e)}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_break",
        description="Set a breakpoint in the Arduino code",
        annotations=ToolAnnotations(
            title="Set Breakpoint",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def debug_break(
        self,
        ctx: Context | None,
        session_id: str,
        location: str,
        condition: Optional[str] = None,
        temporary: bool = False
    ) -> Dict[str, Any]:
        """Set a breakpoint in the debugging session

        Args:
            session_id: Debug session identifier
            location: Function name or file:line
            condition: Optional conditional expression
            temporary: Whether breakpoint is temporary
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            # Validate request
            request = BreakpointRequest(
                location=location,
                condition=condition,
                temporary=temporary
            )

            if ctx:
                await ctx.info(f"🔴 Setting breakpoint at {location}")

            # Send break command to GDB
            break_cmd = f"{'tbreak' if temporary else 'break'} {location}"
            if condition:
                break_cmd += f" if {condition}"

            await self._send_gdb_command(session, break_cmd)

            # Store breakpoint info
            session['breakpoints'].append({
                "location": location,
                "condition": condition,
                "temporary": temporary,
                "id": len(session['breakpoints']) + 1
            })

            if ctx:
                await ctx.debug(f"Breakpoint set at {location}")

            return {
                "success": True,
                "message": f"Breakpoint set at {location}",
                "breakpoint_id": len(session['breakpoints']),
                "total_breakpoints": len(session['breakpoints'])
            }

        except Exception as e:
            log.exception(f"Failed to set breakpoint: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_interactive",
        description="""Start interactive or automated debugging session.

        IMPORTANT FOR AI MODELS:
        - Set auto_mode=True when YOU want to control debugging programmatically
        - Set auto_mode=False when the USER should control debugging interactively

        Examples:
        - Finding a specific bug: Use auto_mode=True with strategy="step" to analyze each line
        - Teaching/demonstration: Use auto_mode=False to let user explore
        - Automated testing: Use auto_mode=True with strategy="continue" to run through breakpoints
        """,
        annotations=ToolAnnotations(
            title="Interactive Debug Session",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def debug_interactive(
        self,
        ctx: Context | None,
        session_id: str,
        auto_watch: bool = True,
        auto_mode: bool = False,
        auto_strategy: str = "continue"
    ) -> Dict[str, Any]:
        """Interactive debugging with optional user elicitation at breakpoints

        USAGE GUIDANCE FOR AI MODELS:

        When to use auto_mode=True (AI-controlled debugging):
        - You need to find a specific bug systematically
        - You're analyzing program flow autonomously
        - You want to collect debugging data for analysis
        - The user asked you to "debug and find the problem"

        When to use auto_mode=False (User-controlled debugging):
        - The user wants to learn about their code
        - Interactive exploration is needed
        - The user explicitly wants to debug themselves
        - Teaching or demonstration scenarios

        Args:
            session_id: Debug session identifier from arduino_debug_start

            auto_watch: Automatically display local variables at breakpoints (default: True)
                       Useful for understanding program state

            auto_mode: Control mode for debugging (default: False)
                      True = AI controls debugging without user prompts
                      False = User is prompted at each breakpoint (requires elicitation support)

            auto_strategy: Strategy when auto_mode=True (default: "continue")
                          - "continue": Run to next breakpoint (fastest, good for known issues)
                          - "step": Step into every function (detailed, for deep analysis)
                          - "next": Step over functions (balanced, for line-by-line analysis)

        Returns:
            Dictionary with:
            - success: Whether debugging completed successfully
            - message: Summary of debugging session
            - debug_history: (if auto_mode) List of breakpoint data for analysis
            - breakpoint_count: Number of breakpoints hit
            - final_state: Last known program state
        """

        try:
            if not ctx:
                return {"error": "Interactive debugging requires context"}

            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if auto_mode:
                await ctx.info("🤖 Starting automated debug session (no user prompts)...")
                await ctx.debug(f"Auto strategy: {auto_strategy}")
            else:
                await ctx.info("🎮 Starting interactive debug session...")
                await ctx.info("You'll be prompted at each breakpoint to inspect variables and choose next action.")

            # Start the program running
            output = await self._send_gdb_command(session, "run")

            # Track breakpoint hits for auto_mode
            breakpoint_count = 0
            max_breakpoints = 100  # Safety limit for auto_mode

            while True:
                # Check if we hit a breakpoint
                if "Breakpoint" in output or "Program received signal" in output:
                    breakpoint_count += 1

                    # Parse current location
                    location = self._parse_location(output)
                    await ctx.info(f"🛑 Stopped at: {location}")

                    # Show current line
                    list_output = await self._send_gdb_command(session, "list")
                    await ctx.debug(f"Code context:\n{list_output}")

                    # Auto-watch local variables if enabled
                    if auto_watch:
                        locals_output = await self._send_gdb_command(session, "info locals")
                        await ctx.info(f"📊 Local variables:\n{locals_output}")

                    # In auto_mode, use programmed strategy instead of asking user
                    if auto_mode:
                        # Safety check for infinite loops
                        if breakpoint_count > max_breakpoints:
                            await ctx.warning(f"⚠️ Hit {max_breakpoints} breakpoints, stopping auto-debug")
                            break

                        # Log the auto action
                        await ctx.debug(f"Auto-executing: {auto_strategy}")

                        # Store debugging info for AI analysis
                        session.setdefault('debug_history', []).append({
                            'breakpoint': breakpoint_count,
                            'location': location,
                            'locals': locals_output if auto_watch else None
                        })

                        # Execute auto strategy
                        action = auto_strategy
                        if auto_strategy == "continue":
                            output = await self._send_gdb_command(session, "continue")
                        elif auto_strategy == "step":
                            output = await self._send_gdb_command(session, "step")
                        elif auto_strategy == "next":
                            output = await self._send_gdb_command(session, "next")
                        else:
                            # Default to continue if unknown strategy
                            output = await self._send_gdb_command(session, "continue")
                        continue  # Skip the user interaction below

                    # Elicit user action (only if not in auto_mode)
                    action = await ctx.ask_user(
                        question="What would you like to do?",
                        choices=[
                            "Continue to next breakpoint",
                            "Step into function",
                            "Step over line",
                            "Inspect variable",
                            "Modify variable",
                            "Show backtrace",
                            "Add breakpoint",
                            "Exit debugging"
                        ],
                        default="Continue to next breakpoint"
                    )

                    # Handle user choice
                    if action == "Continue to next breakpoint":
                        output = await self._send_gdb_command(session, "continue")
                    elif action == "Step into function":
                        output = await self._send_gdb_command(session, "step")
                    elif action == "Step over line":
                        output = await self._send_gdb_command(session, "next")
                    elif action == "Inspect variable":
                        var_name = await ctx.ask_user(
                            question="Enter variable name to inspect:",
                            allow_text=True
                        )
                        var_output = await self._send_gdb_command(session, f"print {var_name}")
                        await ctx.info(f"Value: {var_output}")
                        # Continue where we were
                        continue
                    elif action == "Modify variable":
                        var_expr = await ctx.ask_user(
                            question="Enter assignment (e.g., 'x = 42'):",
                            allow_text=True
                        )
                        set_output = await self._send_gdb_command(session, f"set {var_expr}")
                        await ctx.info(f"Variable modified: {set_output}")
                        continue
                    elif action == "Show backtrace":
                        bt_output = await self._send_gdb_command(session, "backtrace")
                        await ctx.info(f"Call stack:\n{bt_output}")
                        continue
                    elif action == "Add breakpoint":
                        bp_location = await ctx.ask_user(
                            question="Enter breakpoint location (function or file:line):",
                            allow_text=True
                        )
                        bp_output = await self._send_gdb_command(session, f"break {bp_location}")
                        await ctx.info(f"Breakpoint added: {bp_output}")
                        continue
                    elif action == "Exit debugging":
                        await ctx.info("Exiting interactive debug session...")
                        break

                elif "Program exited" in output or "Program terminated" in output:
                    await ctx.info("✅ Program finished execution")
                    break
                elif "No stack" in output:
                    await ctx.warning("⚠️ Program not started yet, running...")
                    output = await self._send_gdb_command(session, "run")
                else:
                    # Program is running, continue
                    output = await self._send_gdb_command(session, "continue")

            # Prepare return data
            result = {
                "success": True,
                "message": "Debugging session completed",
                "breakpoint_count": breakpoint_count,
                "mode": "auto" if auto_mode else "interactive"
            }

            # Include debug history for auto_mode
            if auto_mode and 'debug_history' in session:
                result["debug_history"] = session['debug_history']
                result["message"] = f"Auto-debugging completed. Hit {breakpoint_count} breakpoints."

                # Provide analysis hint for AI models
                result["analysis_hint"] = (
                    "Review debug_history to analyze program flow. "
                    "Each entry contains breakpoint location and local variables. "
                    "Look for unexpected values or state changes."
                )
            else:
                result["message"] = f"Interactive debugging completed. User navigated {breakpoint_count} breakpoints."

            return result

        except Exception as e:
            log.exception(f"Failed in interactive debugging: {e}")
            if ctx:
                await ctx.error(f"Interactive debugging error: {str(e)}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_run",
        description="Run/continue execution in debug session",
        annotations=ToolAnnotations(
            title="Run/Continue Debugging",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def debug_run(
        self,
        ctx: Context | None,
        session_id: str,
        command: str = "continue"
    ) -> Dict[str, Any]:
        """Run or continue execution in debug session

        Args:
            session_id: Debug session identifier
            command: Debug command (run, continue, step, next)
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            # Validate command
            valid_commands = ["run", "continue", "step", "next", "finish"]
            if command not in valid_commands:
                return {"error": f"Invalid command. Use one of: {', '.join(valid_commands)}"}

            if ctx:
                await ctx.info(f"▶️ Executing: {command}")

            # Send command to GDB
            output = await self._send_gdb_command(session, command)

            # Parse output for important info
            stopped_at = None
            if "Breakpoint" in output:
                stopped_at = self._parse_location(output)

                # If context supports elicitation AND we're not being called by AI in automated mode
                # Check for 'auto_inspect' flag that AI can set to disable prompts
                auto_inspect = session.get('auto_inspect', False)

                if ctx and hasattr(ctx, 'ask_confirmation') and not auto_inspect:
                    inspect = await ctx.ask_confirmation(
                        f"Stopped at {stopped_at}. Would you like to inspect variables?",
                        default=False
                    )
                    if inspect:
                        locals_output = await self._send_gdb_command(session, "info locals")
                        await ctx.info(f"Local variables:\n{locals_output}")
                elif auto_inspect:
                    # Auto-inspect for AI analysis
                    locals_output = await self._send_gdb_command(session, "info locals")
                    await ctx.debug(f"Auto-inspected locals: {locals_output}")

            if ctx and stopped_at:
                await ctx.info(f"🛑 Stopped at: {stopped_at}")

            return {
                "success": True,
                "command": command,
                "output": output,
                "stopped_at": stopped_at
            }

        except Exception as e:
            log.exception(f"Failed to execute debug command: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_print",
        description="Print variable value or expression in debug session",
        annotations=ToolAnnotations(
            title="Print Debug Value",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def debug_print(
        self,
        ctx: Context | None,
        session_id: str,
        expression: str
    ) -> Dict[str, Any]:
        """Print variable value or evaluate expression

        Args:
            session_id: Debug session identifier
            expression: Variable name or expression to evaluate
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if ctx:
                await ctx.debug(f"Evaluating: {expression}")

            # Send print command to GDB
            output = await self._send_gdb_command(session, f"print {expression}")

            # Parse value from output
            value = None
            if " = " in output:
                value = output.split(" = ")[-1].strip()

            # Cache the value
            session['variables'][expression] = value

            return {
                "success": True,
                "expression": expression,
                "value": value,
                "raw_output": output
            }

        except Exception as e:
            log.exception(f"Failed to print expression: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_backtrace",
        description="Show call stack backtrace",
        annotations=ToolAnnotations(
            title="Show Backtrace",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def debug_backtrace(
        self,
        ctx: Context | None,
        session_id: str,
        full: bool = False
    ) -> Dict[str, Any]:
        """Show call stack backtrace

        Args:
            session_id: Debug session identifier
            full: Whether to show full backtrace with all frames
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if ctx:
                await ctx.debug("Getting backtrace...")

            # Send backtrace command
            cmd = "backtrace full" if full else "backtrace"
            output = await self._send_gdb_command(session, cmd)

            # Parse stack frames
            frames = []
            for line in output.split('\n'):
                if line.startswith('#'):
                    frames.append(line.strip())

            return {
                "success": True,
                "frames": frames,
                "count": len(frames),
                "raw_output": output
            }

        except Exception as e:
            log.exception(f"Failed to get backtrace: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_list_breakpoints",
        description="List all breakpoints in the debugging session",
        annotations=ToolAnnotations(
            title="List Breakpoints",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def debug_list_breakpoints(
        self,
        ctx: Context | None,
        session_id: str
    ) -> Dict[str, Any]:
        """List all breakpoints with their status

        Args:
            session_id: Debug session identifier

        Returns:
            Dictionary with breakpoint information
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if ctx:
                await ctx.debug("Listing breakpoints...")

            # Get breakpoint info from GDB
            output = await self._send_gdb_command(session, "info breakpoints")

            # Parse breakpoint information
            breakpoints = []
            lines = output.split('\n')
            for line in lines:
                if line and line[0].isdigit():
                    # Parse breakpoint line
                    parts = line.split()
                    if len(parts) >= 3:
                        bp_info = {
                            "id": parts[0],
                            "type": parts[1] if len(parts) > 1 else "breakpoint",
                            "enabled": "y" in line or "enabled" in line.lower(),
                            "location": ' '.join(parts[3:]) if len(parts) > 3 else "unknown"
                        }

                        # Check for conditions
                        if "if " in line:
                            condition_start = line.index("if ") + 3
                            bp_info["condition"] = line[condition_start:].strip()

                        # Check hit count
                        if "hit " in line.lower():
                            import re
                            hits = re.search(r'hit (\d+) time', line.lower())
                            if hits:
                                bp_info["hit_count"] = int(hits.group(1))

                        breakpoints.append(bp_info)

            # Include session's tracked breakpoints for additional info
            tracked = session.get('breakpoints', [])

            return {
                "success": True,
                "count": len(breakpoints),
                "breakpoints": breakpoints,
                "tracked_breakpoints": tracked,
                "raw_output": output
            }

        except Exception as e:
            log.exception(f"Failed to list breakpoints: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_delete_breakpoint",
        description="Delete a breakpoint by ID or all breakpoints",
        annotations=ToolAnnotations(
            title="Delete Breakpoint",
            destructiveHint=True,
            idempotentHint=True,
        )
    )
    async def debug_delete_breakpoint(
        self,
        ctx: Context | None,
        session_id: str,
        breakpoint_id: Optional[str] = None,
        delete_all: bool = False
    ) -> Dict[str, Any]:
        """Delete one or all breakpoints

        Args:
            session_id: Debug session identifier
            breakpoint_id: Specific breakpoint ID to delete
            delete_all: Delete all breakpoints if True

        Returns:
            Dictionary with deletion status
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if delete_all:
                if ctx:
                    await ctx.info("🗑️ Deleting all breakpoints...")
                output = await self._send_gdb_command(session, "delete")
                session['breakpoints'] = []  # Clear tracked list
                return {
                    "success": True,
                    "message": "All breakpoints deleted",
                    "output": output
                }
            elif breakpoint_id:
                if ctx:
                    await ctx.info(f"🗑️ Deleting breakpoint {breakpoint_id}...")
                output = await self._send_gdb_command(session, f"delete {breakpoint_id}")

                # Remove from tracked list
                session['breakpoints'] = [
                    bp for bp in session.get('breakpoints', [])
                    if str(bp.get('id')) != str(breakpoint_id)
                ]

                return {
                    "success": True,
                    "message": f"Breakpoint {breakpoint_id} deleted",
                    "output": output
                }
            else:
                return {"error": "Specify breakpoint_id or set delete_all=True"}

        except Exception as e:
            log.exception(f"Failed to delete breakpoint: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_enable_breakpoint",
        description="Enable or disable a breakpoint",
        annotations=ToolAnnotations(
            title="Enable/Disable Breakpoint",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def debug_enable_breakpoint(
        self,
        ctx: Context | None,
        session_id: str,
        breakpoint_id: str,
        enable: bool = True
    ) -> Dict[str, Any]:
        """Enable or disable a breakpoint

        Args:
            session_id: Debug session identifier
            breakpoint_id: Breakpoint ID to modify
            enable: True to enable, False to disable

        Returns:
            Dictionary with operation status
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            command = "enable" if enable else "disable"
            status = "enabled" if enable else "disabled"
            emoji = "✅" if enable else "⏸️"

            if ctx:
                await ctx.info(f"{emoji} {command.capitalize()}ing breakpoint {breakpoint_id}...")

            output = await self._send_gdb_command(session, f"{command} {breakpoint_id}")

            return {
                "success": True,
                "message": f"Breakpoint {breakpoint_id} {status}",
                "enabled": enable,
                "output": output
            }

        except Exception as e:
            log.exception(f"Failed to {command} breakpoint: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_condition_breakpoint",
        description="Add or modify a condition on a breakpoint",
        annotations=ToolAnnotations(
            title="Set Breakpoint Condition",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def debug_condition_breakpoint(
        self,
        ctx: Context | None,
        session_id: str,
        breakpoint_id: str,
        condition: str
    ) -> Dict[str, Any]:
        """Set or modify a breakpoint condition

        Args:
            session_id: Debug session identifier
            breakpoint_id: Breakpoint ID to modify
            condition: Condition expression (e.g., "i > 10", "x == 42")
                      Empty string to remove condition

        Returns:
            Dictionary with operation status
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if ctx:
                if condition:
                    await ctx.info(f"🎯 Setting condition on breakpoint {breakpoint_id}: {condition}")
                else:
                    await ctx.info(f"🎯 Removing condition from breakpoint {breakpoint_id}")

            # Set or clear condition
            if condition:
                output = await self._send_gdb_command(session, f"condition {breakpoint_id} {condition}")
                message = f"Condition '{condition}' set on breakpoint {breakpoint_id}"
            else:
                output = await self._send_gdb_command(session, f"condition {breakpoint_id}")
                message = f"Condition removed from breakpoint {breakpoint_id}"

            # Update tracked breakpoints
            for bp in session.get('breakpoints', []):
                if str(bp.get('id')) == str(breakpoint_id):
                    bp['condition'] = condition if condition else None
                    break

            return {
                "success": True,
                "message": message,
                "breakpoint_id": breakpoint_id,
                "condition": condition if condition else None,
                "output": output
            }

        except Exception as e:
            log.exception(f"Failed to set breakpoint condition: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_save_breakpoints",
        description="Save current breakpoints to a file for later reuse",
        annotations=ToolAnnotations(
            title="Save Breakpoints",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def debug_save_breakpoints(
        self,
        ctx: Context | None,
        session_id: str,
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Save breakpoints to a file for later restoration

        Args:
            session_id: Debug session identifier
            filename: Optional filename (defaults to sketch_name.bkpts)

        Returns:
            Dictionary with save status and file path
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            # Generate filename if not provided
            if not filename:
                sketch_name = session.get('sketch', 'debug')
                filename = f"{sketch_name}.bkpts"

            # Get breakpoint commands to save
            if ctx:
                await ctx.info(f"💾 Saving breakpoints to {filename}...")

            output = await self._send_gdb_command(session, f"save breakpoints {filename}")

            # Also save our tracked metadata
            import json
            metadata_file = Path(filename).with_suffix('.meta.json')
            metadata = {
                'sketch': session.get('sketch'),
                'breakpoints': session.get('breakpoints', []),
                'saved_at': str(Path(filename).stat().st_mtime) if Path(filename).exists() else None
            }

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            return {
                "success": True,
                "message": f"Breakpoints saved to {filename}",
                "file": str(Path(filename).absolute()),
                "metadata_file": str(metadata_file.absolute()),
                "count": len(session.get('breakpoints', []))
            }

        except Exception as e:
            log.exception(f"Failed to save breakpoints: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_restore_breakpoints",
        description="Restore previously saved breakpoints",
        annotations=ToolAnnotations(
            title="Restore Breakpoints",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def debug_restore_breakpoints(
        self,
        ctx: Context | None,
        session_id: str,
        filename: str
    ) -> Dict[str, Any]:
        """Restore breakpoints from a saved file

        Args:
            session_id: Debug session identifier
            filename: Path to breakpoints file

        Returns:
            Dictionary with restoration status
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if not Path(filename).exists():
                return {"error": f"Breakpoint file '{filename}' not found"}

            if ctx:
                await ctx.info(f"📂 Restoring breakpoints from {filename}...")

            # Restore breakpoints in GDB
            output = await self._send_gdb_command(session, f"source {filename}")

            # Try to restore metadata if available
            metadata_file = Path(filename).with_suffix('.meta.json')
            if metadata_file.exists():
                import json
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    session['breakpoints'] = metadata.get('breakpoints', [])

                if ctx:
                    await ctx.debug(f"Restored {len(session['breakpoints'])} breakpoint metadata entries")

            return {
                "success": True,
                "message": f"Breakpoints restored from {filename}",
                "output": output,
                "restored_count": len(session.get('breakpoints', []))
            }

        except Exception as e:
            log.exception(f"Failed to restore breakpoints: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_watch",
        description="Add a watch expression to monitor variable changes",
        annotations=ToolAnnotations(
            title="Add Watch Expression",
            destructiveHint=False,
            idempotentHint=False,
        )
    )
    async def debug_watch(
        self,
        ctx: Context | None,
        session_id: str,
        expression: str
    ) -> Dict[str, Any]:
        """Add a watch expression to monitor changes

        Args:
            session_id: Debug session identifier
            expression: Variable or expression to watch
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if ctx:
                await ctx.info(f"👁️ Adding watch: {expression}")

            # Send watch command
            output = await self._send_gdb_command(session, f"watch {expression}")

            # Store watch info
            if 'watches' not in session:
                session['watches'] = []

            session['watches'].append({
                "expression": expression,
                "id": len(session['watches']) + 1
            })

            return {
                "success": True,
                "message": f"Watch added for: {expression}",
                "watch_id": len(session['watches']),
                "total_watches": len(session['watches'])
            }

        except Exception as e:
            log.exception(f"Failed to add watch: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_memory",
        description="Examine memory contents at address",
        annotations=ToolAnnotations(
            title="Examine Memory",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def debug_memory(
        self,
        ctx: Context | None,
        session_id: str,
        address: str,
        count: int = 16,
        format: str = "hex"
    ) -> Dict[str, Any]:
        """Examine memory contents

        Args:
            session_id: Debug session identifier
            address: Memory address or pointer variable
            count: Number of units to display
            format: Display format (hex, decimal, binary, char)
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            # Map format to GDB format specifier
            format_map = {
                "hex": "x",
                "decimal": "d",
                "binary": "t",
                "char": "c",
                "string": "s"
            }

            gdb_format = format_map.get(format, "x")

            if ctx:
                await ctx.debug(f"Examining memory at {address}")

            # Send examine command
            cmd = f"x/{count}{gdb_format} {address}"
            output = await self._send_gdb_command(session, cmd)

            return {
                "success": True,
                "address": address,
                "count": count,
                "format": format,
                "memory": output
            }

        except Exception as e:
            log.exception(f"Failed to examine memory: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_stop",
        description="Stop and cleanup debug session",
        annotations=ToolAnnotations(
            title="Stop Debug Session",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def debug_stop(
        self,
        ctx: Context | None,
        session_id: str
    ) -> Dict[str, Any]:
        """Stop and cleanup debug session

        Args:
            session_id: Debug session identifier
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if ctx:
                await ctx.info(f"🛑 Stopping debug session: {session_id}")
                await ctx.report_progress(50, 100)

            # Send quit command to GDB
            if session['process']:
                try:
                    await self._send_gdb_command(session, "quit")
                    await asyncio.wait_for(session['process'].wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    session['process'].terminate()
                    await session['process'].wait()

            # Remove session
            del self.debug_sessions[session_id]

            if ctx:
                await ctx.report_progress(100, 100)
                await ctx.info("✅ Debug session stopped")

            return {
                "success": True,
                "message": f"Debug session '{session_id}' stopped"
            }

        except Exception as e:
            log.exception(f"Failed to stop debug session: {e}")
            return {"error": str(e)}

    @mcp_tool(
        name="arduino_debug_registers",
        description="Show CPU register values",
        annotations=ToolAnnotations(
            title="Show Registers",
            destructiveHint=False,
            idempotentHint=True,
        )
    )
    async def debug_registers(
        self,
        ctx: Context | None,
        session_id: str
    ) -> Dict[str, Any]:
        """Show current CPU register values

        Args:
            session_id: Debug session identifier
        """

        try:
            if session_id not in self.debug_sessions:
                return {"error": f"No debug session found: {session_id}"}

            session = self.debug_sessions[session_id]

            if ctx:
                await ctx.debug("Reading CPU registers...")

            # Get register info
            output = await self._send_gdb_command(session, "info registers")

            # Parse register values
            registers = {}
            for line in output.split('\n'):
                parts = line.split()
                if len(parts) >= 2 and not line.startswith(' '):
                    reg_name = parts[0]
                    reg_value = parts[1]
                    registers[reg_name] = reg_value

            return {
                "success": True,
                "registers": registers,
                "count": len(registers),
                "raw_output": output
            }

        except Exception as e:
            log.exception(f"Failed to get registers: {e}")
            return {"error": str(e)}

    def _parse_location(self, output: str) -> str:
        """Parse location from GDB output"""
        lines = output.split('\n')
        for line in lines:
            if " at " in line:
                return line.split(" at ")[-1].strip()
            elif "in " in line and "(" in line:
                # Function name with file location
                return line.strip()
        return "unknown location"

    async def _send_gdb_command(self, session: Dict, command: str) -> str:
        """Send command to GDB process and return output"""

        process = session['process']
        if not process or process.returncode is not None:
            raise Exception("Debug process not running")

        # Send command
        process.stdin.write(f"{command}\n".encode())
        await process.stdin.drain()

        # Read output (with timeout)
        output = ""
        try:
            while True:
                line = await asyncio.wait_for(
                    process.stdout.readline(),
                    timeout=2.0
                )
                if not line:
                    break
                decoded = line.decode()
                output += decoded
                if "(gdb)" in decoded:  # GDB prompt
                    break
        except asyncio.TimeoutError:
            pass

        return output.strip()