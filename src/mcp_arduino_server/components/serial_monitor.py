"""
Serial Monitor Component with FastMCP Integration
Provides cursor-based serial data access with context management
"""

import asyncio
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum

from fastmcp import Context
from fastmcp.tools import Tool
from pydantic import BaseModel, Field

from .serial_manager import SerialConnectionManager


class SerialDataType(str, Enum):
    """Types of serial data entries"""
    RECEIVED = "received"
    SENT = "sent"
    SYSTEM = "system"
    ERROR = "error"


@dataclass
class SerialDataEntry:
    """A single serial data entry"""
    timestamp: str
    type: SerialDataType
    data: str
    port: str
    index: int

    def to_dict(self) -> dict:
        return asdict(self)


class SerialDataBuffer:
    """
    Circular buffer with cursor support for serial data
    Provides efficient pagination and data retrieval
    """

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.buffer: list[SerialDataEntry] = []
        self.global_index = 0  # Ever-incrementing index
        self.cursors: dict[str, int] = {}  # cursor_id -> position

    def add_entry(self, port: str, data: str, data_type: SerialDataType = SerialDataType.RECEIVED):
        """Add a new entry to the buffer"""
        entry = SerialDataEntry(
            timestamp=datetime.now().isoformat(),
            type=data_type,
            data=data,
            port=port,
            index=self.global_index
        )
        self.global_index += 1

        self.buffer.append(entry)

        # Maintain circular buffer
        if len(self.buffer) > self.max_size:
            self.buffer.pop(0)

    def create_cursor(self, start_index: int | None = None) -> str:
        """Create a new cursor for reading data"""
        cursor_id = str(uuid.uuid4())

        if start_index is not None:
            self.cursors[cursor_id] = start_index
        elif self.buffer:
            # Start from oldest available entry
            self.cursors[cursor_id] = self.buffer[0].index
        else:
            # Start from next entry
            self.cursors[cursor_id] = self.global_index

        return cursor_id

    def read_from_cursor(
        self,
        cursor_id: str,
        limit: int = 100,
        port_filter: str | None = None,
        type_filter: SerialDataType | None = None
    ) -> tuple[list[SerialDataEntry], bool]:
        """
        Read entries from cursor position

        Returns:
            Tuple of (entries, has_more)
        """
        if cursor_id not in self.cursors:
            return [], False

        cursor_pos = self.cursors[cursor_id]
        entries = []

        for entry in self.buffer:
            # Skip entries before cursor
            if entry.index < cursor_pos:
                continue

            # Apply filters
            if port_filter and entry.port != port_filter:
                continue
            if type_filter and entry.type != type_filter:
                continue

            entries.append(entry)

            if len(entries) >= limit:
                break

        # Update cursor position
        if entries:
            self.cursors[cursor_id] = entries[-1].index + 1

        # Check if there's more data
        has_more = False
        if entries and entries[-1].index < self.global_index - 1:
            has_more = True

        return entries, has_more

    def delete_cursor(self, cursor_id: str):
        """Delete a cursor"""
        self.cursors.pop(cursor_id, None)

    def get_latest(self, port: str | None = None, limit: int = 10) -> list[SerialDataEntry]:
        """Get latest entries without cursor"""
        entries = self.buffer[-limit:] if not port else [
            e for e in self.buffer if e.port == port
        ][-limit:]
        return entries

    def clear(self, port: str | None = None):
        """Clear buffer for a specific port or all"""
        if port:
            self.buffer = [e for e in self.buffer if e.port != port]
        else:
            self.buffer.clear()


class SerialMonitorContext:
    """FastMCP context for serial monitoring"""

    def __init__(self):
        self.connection_manager = SerialConnectionManager()
        self.data_buffer = SerialDataBuffer()
        self.active_monitors: dict[str, asyncio.Task] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize the serial monitor context"""
        if not self._initialized:
            await self.connection_manager.start()
            self._initialized = True

    async def cleanup(self):
        """Cleanup resources"""
        if self._initialized:
            await self.connection_manager.stop()
            self._initialized = False

    def get_state(self) -> dict:
        """Get current state for FastMCP context"""
        connected_ports = self.connection_manager.get_connected_ports()
        state = {
            "connected_ports": connected_ports,
            "active_monitors": list(self.active_monitors.keys()),
            "buffer_size": len(self.data_buffer.buffer),
            "active_cursors": len(self.data_buffer.cursors),
            "connections": {}
        }

        # Add connection details
        for port in connected_ports:
            conn = self.connection_manager.get_connection(port)
            if conn:
                state["connections"][port] = {
                    "state": conn.state.value,
                    "baudrate": conn.baudrate,
                    "last_activity": conn.last_activity.isoformat() if conn.last_activity else None,
                    "error": conn.error_message
                }

        return state


# Pydantic models for tool inputs/outputs

class SerialConnectParams(BaseModel):
    """Parameters for connecting to a serial port"""
    port: str = Field(..., description="Serial port path (e.g., /dev/ttyUSB0 or COM3)")
    baudrate: int = Field(115200, description="Baud rate")
    auto_monitor: bool = Field(True, description="Start monitoring automatically")
    exclusive: bool = Field(False, description="Disconnect other ports first")


class SerialDisconnectParams(BaseModel):
    """Parameters for disconnecting from a serial port"""
    port: str = Field(..., description="Serial port to disconnect")


class SerialSendParams(BaseModel):
    """Parameters for sending data to a serial port"""
    port: str = Field(..., description="Serial port")
    data: str = Field(..., description="Data to send")
    add_newline: bool = Field(True, description="Add newline at the end")
    wait_response: bool = Field(False, description="Wait for response")
    timeout: float = Field(5.0, description="Response timeout in seconds")


class SerialReadParams(BaseModel):
    """Parameters for reading serial data"""
    cursor_id: str | None = Field(None, description="Cursor ID for pagination")
    port: str | None = Field(None, description="Filter by port")
    limit: int = Field(100, description="Maximum entries to return")
    type_filter: SerialDataType | None = Field(None, description="Filter by data type")
    create_cursor: bool = Field(False, description="Create new cursor if not provided")


class SerialListPortsParams(BaseModel):
    """Parameters for listing serial ports"""
    arduino_only: bool = Field(False, description="List only Arduino-compatible ports")


class SerialClearBufferParams(BaseModel):
    """Parameters for clearing serial buffer"""
    port: str | None = Field(None, description="Clear specific port or all if None")


class SerialResetBoardParams(BaseModel):
    """Parameters for resetting a board"""
    port: str = Field(..., description="Serial port of the board")
    method: str = Field("dtr", description="Reset method: dtr, rts, or 1200bps")


# FastMCP Tools for serial monitoring

class SerialConnectTool(Tool):
    """Connect to a serial port"""
    name: str = "serial_connect"
    description: str = "Connect to a serial port for monitoring"
    parameters: type = SerialConnectParams

    async def run(self, params: SerialConnectParams, ctx: Context) -> dict:
        monitor = ctx.state.get("serial_monitor")
        if not monitor:
            monitor = SerialMonitorContext()
            await monitor.initialize()
            ctx.state["serial_monitor"] = monitor

        try:
            # Connect to port
            conn = await monitor.connection_manager.connect(
                port=params.port,
                baudrate=params.baudrate,
                auto_monitor=params.auto_monitor,
                exclusive=params.exclusive
            )

            # Set up data listener
            async def on_data_received(line: str):
                monitor.data_buffer.add_entry(params.port, line, SerialDataType.RECEIVED)

            conn.add_listener(on_data_received)

            # Add system message
            monitor.data_buffer.add_entry(
                params.port,
                f"Connected at {params.baudrate} baud",
                SerialDataType.SYSTEM
            )

            return {
                "success": True,
                "port": params.port,
                "baudrate": params.baudrate,
                "state": conn.state.value
            }

        except Exception as e:
            # Log error
            monitor.data_buffer.add_entry(
                params.port,
                str(e),
                SerialDataType.ERROR
            )
            return {
                "success": False,
                "error": str(e)
            }


class SerialDisconnectTool(Tool):
    """Disconnect from a serial port"""
    name: str = "serial_disconnect"
    description: str = "Disconnect from a serial port"
    parameters: type = SerialDisconnectParams

    async def run(self, params: SerialDisconnectParams, ctx: Context) -> dict:
        monitor = ctx.state.get("serial_monitor")
        if not monitor:
            return {"success": False, "error": "Serial monitor not initialized"}

        success = await monitor.connection_manager.disconnect(params.port)

        if success:
            monitor.data_buffer.add_entry(
                params.port,
                "Disconnected",
                SerialDataType.SYSTEM
            )

        return {"success": success, "port": params.port}


class SerialSendTool(Tool):
    """Send data to a serial port"""
    name: str = "serial_send"
    description: str = "Send data to a connected serial port"
    parameters: type = SerialSendParams

    async def run(self, params: SerialSendParams, ctx: Context) -> dict:
        monitor = ctx.state.get("serial_monitor")
        if not monitor:
            return {"success": False, "error": "Serial monitor not initialized"}

        # Log sent data
        monitor.data_buffer.add_entry(
            params.port,
            params.data,
            SerialDataType.SENT
        )

        # Send via connection manager
        if params.wait_response:
            response = await monitor.connection_manager.send_command(
                params.port,
                params.data if not params.add_newline else params.data + "\n",
                wait_for_response=True,
                timeout=params.timeout
            )
            return {
                "success": response is not None,
                "response": response
            }
        else:
            conn = monitor.connection_manager.get_connection(params.port)
            if conn:
                if params.add_newline:
                    success = await conn.writeline(params.data)
                else:
                    success = await conn.write(params.data)
                return {"success": success}
            return {"success": False, "error": "Port not connected"}


class SerialReadTool(Tool):
    """Read serial data with cursor support"""
    name: str = "serial_read"
    description: str = "Read serial data using cursor-based pagination"
    parameters: type = SerialReadParams

    async def run(self, params: SerialReadParams, ctx: Context) -> dict:
        monitor = ctx.state.get("serial_monitor")
        if not monitor:
            return {"success": False, "error": "Serial monitor not initialized"}

        # Handle cursor
        cursor_id = params.cursor_id
        if params.create_cursor and not cursor_id:
            cursor_id = monitor.data_buffer.create_cursor()

        if cursor_id:
            # Read from cursor
            entries, has_more = monitor.data_buffer.read_from_cursor(
                cursor_id,
                params.limit,
                params.port,
                params.type_filter
            )

            return {
                "success": True,
                "cursor_id": cursor_id,
                "has_more": has_more,
                "entries": [e.to_dict() for e in entries],
                "count": len(entries)
            }
        else:
            # Get latest without cursor
            entries = monitor.data_buffer.get_latest(params.port, params.limit)
            return {
                "success": True,
                "entries": [e.to_dict() for e in entries],
                "count": len(entries)
            }


class SerialListPortsTool(Tool):
    """List available serial ports"""
    name: str = "serial_list_ports"
    description: str = "List available serial ports"
    parameters: type = SerialListPortsParams

    async def run(self, params: SerialListPortsParams, ctx: Context) -> dict:
        monitor = ctx.state.get("serial_monitor")
        if not monitor:
            monitor = SerialMonitorContext()
            await monitor.initialize()
            ctx.state["serial_monitor"] = monitor

        if params.arduino_only:
            ports = await monitor.connection_manager.list_arduino_ports()
        else:
            ports = await monitor.connection_manager.list_ports()

        return {
            "success": True,
            "ports": [
                {
                    "device": p.device,
                    "description": p.description,
                    "hwid": p.hwid,
                    "vid": p.vid,
                    "pid": p.pid,
                    "serial_number": p.serial_number,
                    "manufacturer": p.manufacturer,
                    "product": p.product,
                    "is_arduino": p.is_arduino_compatible()
                }
                for p in ports
            ]
        }


class SerialClearBufferTool(Tool):
    """Clear serial data buffer"""
    name: str = "serial_clear_buffer"
    description: str = "Clear serial data buffer"
    parameters: type = SerialClearBufferParams

    async def run(self, params: SerialClearBufferParams, ctx: Context) -> dict:
        monitor = ctx.state.get("serial_monitor")
        if not monitor:
            return {"success": False, "error": "Serial monitor not initialized"}

        monitor.data_buffer.clear(params.port)
        return {"success": True, "cleared": params.port or "all"}


class SerialResetBoardTool(Tool):
    """Reset an Arduino board"""
    name: str = "serial_reset_board"
    description: str = "Reset an Arduino board using DTR, RTS, or 1200bps touch"
    parameters: type = SerialResetBoardParams

    async def run(self, params: SerialResetBoardParams, ctx: Context) -> dict:
        monitor = ctx.state.get("serial_monitor")
        if not monitor:
            return {"success": False, "error": "Serial monitor not initialized"}

        success = await monitor.connection_manager.reset_board(
            params.port,
            params.method
        )

        if success:
            monitor.data_buffer.add_entry(
                params.port,
                f"Board reset using {params.method} method",
                SerialDataType.SYSTEM
            )

        return {"success": success, "method": params.method}


class SerialMonitorStateParams(BaseModel):
    """Parameters for getting serial monitor state (none required)"""
    pass


class SerialMonitorStateTool(Tool):
    """Get serial monitor state"""
    name: str = "serial_monitor_state"
    description: str = "Get current state of serial monitor"
    parameters: type = SerialMonitorStateParams

    async def run(self, params: SerialMonitorStateParams, ctx: Context) -> dict:
        monitor = ctx.state.get("serial_monitor")
        if not monitor:
            return {"initialized": False}

        state = monitor.get_state()
        state["initialized"] = True
        return state


# Export tools
SERIAL_TOOLS = [
    SerialConnectTool(),
    SerialDisconnectTool(),
    SerialSendTool(),
    SerialReadTool(),
    SerialListPortsTool(),
    SerialClearBufferTool(),
    SerialResetBoardTool(),
    SerialMonitorStateTool(),
]
