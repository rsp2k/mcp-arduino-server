"""
Arduino Serial Monitor Component using MCPMixin pattern
Provides serial communication with cursor-based data streaming
"""

import asyncio
import os

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_resource, mcp_tool
from pydantic import Field

from .circular_buffer import CircularSerialBuffer, SerialDataType
from .serial_manager import SerialConnectionManager

# Use CircularSerialBuffer directly
SerialDataBuffer = CircularSerialBuffer


class ArduinoSerial(MCPMixin):
    """Arduino Serial Monitor component with MCPMixin pattern"""

    def __init__(self, config):
        """Initialize serial monitor with configuration"""
        self.config = config
        self.connection_manager = SerialConnectionManager()

        # Get buffer size from environment variable with sane default
        buffer_size = int(os.environ.get('ARDUINO_SERIAL_BUFFER_SIZE', '10000'))
        # Enforce reasonable limits
        buffer_size = max(100, min(buffer_size, 1000000))  # Between 100 and 1M entries

        self.data_buffer = CircularSerialBuffer(max_size=buffer_size)
        self.active_monitors: dict[str, asyncio.Task] = {}
        self._initialized = False

        # Log buffer configuration
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Serial buffer initialized with size: {buffer_size} entries")

    async def initialize(self):
        """Initialize the serial monitor"""
        if not self._initialized:
            await self.connection_manager.start()
            self._initialized = True

    async def cleanup(self):
        """Cleanup resources"""
        if self._initialized:
            await self.connection_manager.stop()
            self._initialized = False

    def get_state(self) -> dict:
        """Get current state for context"""
        connected_ports = self.connection_manager.get_connected_ports()
        state = {
            "connected_ports": connected_ports,
            "active_monitors": list(self.active_monitors.keys()),
            "buffer_size": len(self.data_buffer.buffer),
            "active_cursors": len(self.data_buffer.cursors),
            "connections": {}
        }

        for port in connected_ports:
            conn = self.connection_manager.get_connection(port)
            if conn:
                state["connections"][port] = {
                    "state": conn.state.value,
                    "baudrate": conn.baudrate,
                    "config": f"{conn.bytesize}-{conn.parity}-{conn.stopbits}",
                    "flow_control": {
                        "xonxoff": conn.xonxoff,
                        "rtscts": conn.rtscts,
                        "dsrdtr": conn.dsrdtr
                    },
                    "last_activity": conn.last_activity.isoformat() if conn.last_activity else None,
                    "error": conn.error_message
                }

        return state

    @mcp_resource(uri="arduino://serial/state")
    async def get_serial_state_resource(self) -> str:
        """Get current serial monitor state as a resource"""
        import json
        state = self.get_state()
        return f"""# Serial Monitor State

## Overview
- Connected Ports: {len(state['connected_ports'])}
- Active Monitors: {len(state['active_monitors'])}
- Buffer Size: {state['buffer_size']} entries
- Active Cursors: {state['active_cursors']}

## Connections
{json.dumps(state['connections'], indent=2)}
"""

    @mcp_tool(name="serial_connect", description="Connect to a serial port for monitoring")
    async def connect(
        self,
        port: str = Field(..., description="Serial port path (e.g., /dev/ttyUSB0)"),
        baudrate: int = Field(115200, description="Baud rate (9600, 19200, 38400, 57600, 115200, etc.)"),
        bytesize: int = Field(8, description="Number of data bits (5, 6, 7, or 8)"),
        parity: str = Field('N', description="Parity: 'N'=None, 'E'=Even, 'O'=Odd, 'M'=Mark, 'S'=Space"),
        stopbits: float = Field(1, description="Number of stop bits (1, 1.5, or 2)"),
        xonxoff: bool = Field(False, description="Enable software (XON/XOFF) flow control"),
        rtscts: bool = Field(False, description="Enable hardware (RTS/CTS) flow control"),
        dsrdtr: bool = Field(False, description="Enable hardware (DSR/DTR) flow control"),
        auto_monitor: bool = Field(True, description="Start monitoring automatically"),
        exclusive: bool = Field(False, description="Disconnect other ports first"),
        ctx: Context = None
    ) -> dict:
        """Connect to a serial port"""
        if not self._initialized:
            await self.initialize()

        try:
            conn = await self.connection_manager.connect(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                xonxoff=xonxoff,
                rtscts=rtscts,
                dsrdtr=dsrdtr,
                auto_monitor=auto_monitor,
                exclusive=exclusive
            )

            async def on_data_received(line: str):
                self.data_buffer.add_entry(port, line, SerialDataType.RECEIVED)

            conn.add_listener(on_data_received)
            self.data_buffer.add_entry(port, f"Connected at {baudrate} baud", SerialDataType.SYSTEM)

            return {
                "success": True,
                "port": port,
                "baudrate": baudrate,
                "config": f"{bytesize}-{parity}-{stopbits}",
                "flow_control": {
                    "xonxoff": xonxoff,
                    "rtscts": rtscts,
                    "dsrdtr": dsrdtr
                },
                "state": conn.state.value
            }
        except Exception as e:
            self.data_buffer.add_entry(port, str(e), SerialDataType.ERROR)
            return {"success": False, "error": str(e)}

    @mcp_tool(name="serial_disconnect", description="Disconnect from a serial port")
    async def disconnect(
        self,
        port: str = Field(..., description="Serial port to disconnect"),
        ctx: Context = None
    ) -> dict:
        """Disconnect from a serial port"""
        success = await self.connection_manager.disconnect(port)
        if success:
            self.data_buffer.add_entry(port, "Disconnected", SerialDataType.SYSTEM)
        return {"success": success, "port": port}

    @mcp_tool(name="serial_send", description="Send data to a connected serial port")
    async def send(
        self,
        port: str = Field(..., description="Serial port"),
        data: str = Field(..., description="Data to send"),
        add_newline: bool = Field(True, description="Add newline at the end"),
        wait_response: bool = Field(False, description="Wait for response"),
        timeout: float = Field(5.0, description="Response timeout in seconds"),
        ctx: Context = None
    ) -> dict:
        """Send data to a serial port"""
        self.data_buffer.add_entry(port, data, SerialDataType.SENT)

        if wait_response:
            response = await self.connection_manager.send_command(
                port, data if not add_newline else data + "\n",
                wait_for_response=True, timeout=timeout
            )
            return {"success": response is not None, "response": response}
        else:
            conn = self.connection_manager.get_connection(port)
            if conn:
                if add_newline:
                    success = await conn.writeline(data)
                else:
                    success = await conn.write(data)
                return {"success": success}
            return {"success": False, "error": "Port not connected"}

    @mcp_tool(name="serial_read", description="Read serial data using cursor-based pagination")
    async def read(
        self,
        cursor_id: str | None = Field(None, description="Cursor ID for pagination"),
        port: str | None = Field(None, description="Filter by port"),
        limit: int = Field(100, description="Maximum entries to return"),
        type_filter: str | None = Field(None, description="Filter by data type"),
        create_cursor: bool = Field(False, description="Create new cursor if not provided"),
        start_from: str = Field("oldest", description="Where to start cursor: oldest, newest, next"),
        auto_recover: bool = Field(True, description="Auto-recover invalid cursors"),
        ctx: Context = None
    ) -> dict:
        """Read serial data with enhanced circular buffer support"""
        # Create cursor if requested
        if create_cursor and not cursor_id:
            cursor_id = self.data_buffer.create_cursor(start_from=start_from)

        if cursor_id:
            # Read from cursor with circular buffer features
            type_filter_enum = SerialDataType(type_filter) if type_filter else None
            result = self.data_buffer.read_from_cursor(
                cursor_id=cursor_id,
                limit=limit,
                port_filter=port,
                type_filter=type_filter_enum,
                auto_recover=auto_recover
            )
            return result
        else:
            # Get latest without cursor
            entries = self.data_buffer.get_latest(port, limit)
            stats = self.data_buffer.get_statistics()
            return {
                "success": True,
                "entries": [e.to_dict() for e in entries],
                "count": len(entries),
                "buffer_stats": stats
            }

    @mcp_tool(name="serial_list_ports", description="List available serial ports")
    async def list_ports(
        self,
        arduino_only: bool = Field(False, description="List only Arduino-compatible ports"),
        ctx: Context = None
    ) -> dict:
        """List available serial ports"""
        if not self._initialized:
            await self.initialize()

        if arduino_only:
            ports = await self.connection_manager.list_arduino_ports()
        else:
            ports = await self.connection_manager.list_ports()

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

    @mcp_tool(name="serial_clear_buffer", description="Clear serial data buffer")
    async def clear_buffer(
        self,
        port: str | None = Field(None, description="Clear specific port or all if None"),
        ctx: Context = None
    ) -> dict:
        """Clear serial data buffer"""
        self.data_buffer.clear(port)
        return {"success": True, "cleared": port or "all"}

    @mcp_tool(name="serial_reset_board", description="Reset an Arduino board using DTR, RTS, or 1200bps touch")
    async def reset_board(
        self,
        port: str = Field(..., description="Serial port of the board"),
        method: str = Field("dtr", description="Reset method: dtr, rts, or 1200bps"),
        ctx: Context = None
    ) -> dict:
        """Reset an Arduino board"""
        success = await self.connection_manager.reset_board(port, method)
        if success:
            self.data_buffer.add_entry(
                port, f"Board reset using {method} method", SerialDataType.SYSTEM
            )
        return {"success": success, "method": method}

    @mcp_tool(name="serial_monitor_state", description="Get current state of serial monitor")
    async def monitor_state(self, ctx: Context = None) -> dict:
        """Get serial monitor state"""
        if not self._initialized:
            return {"initialized": False}

        state = self.get_state()
        state["initialized"] = True
        state["buffer_stats"] = self.data_buffer.get_statistics()
        return state

    @mcp_tool(name="serial_cursor_info", description="Get information about a cursor")
    async def cursor_info(
        self,
        cursor_id: str = Field(..., description="Cursor ID to get info for"),
        ctx: Context = None
    ) -> dict:
        """Get cursor information"""
        info = self.data_buffer.get_cursor_info(cursor_id)
        if info:
            return {"success": True, **info}
        return {"success": False, "error": "Cursor not found"}

    @mcp_tool(name="serial_list_cursors", description="List all active cursors")
    async def list_cursors(self, ctx: Context = None) -> dict:
        """List all active cursors"""
        cursors = self.data_buffer.list_cursors()
        return {
            "success": True,
            "cursors": cursors,
            "count": len(cursors)
        }

    @mcp_tool(name="serial_delete_cursor", description="Delete a cursor")
    async def delete_cursor(
        self,
        cursor_id: str = Field(..., description="Cursor ID to delete"),
        ctx: Context = None
    ) -> dict:
        """Delete a cursor"""
        success = self.data_buffer.delete_cursor(cursor_id)
        return {"success": success}

    @mcp_tool(name="serial_cleanup_cursors", description="Remove all invalid cursors")
    async def cleanup_cursors(self, ctx: Context = None) -> dict:
        """Cleanup invalid cursors"""
        removed = self.data_buffer.cleanup_invalid_cursors()
        return {
            "success": True,
            "removed": removed
        }

    @mcp_tool(name="serial_buffer_stats", description="Get buffer statistics")
    async def buffer_stats(self, ctx: Context = None) -> dict:
        """Get detailed buffer statistics"""
        stats = self.data_buffer.get_statistics()
        return {"success": True, **stats}

    @mcp_tool(name="serial_resize_buffer", description="Resize the circular buffer")
    async def resize_buffer(
        self,
        new_size: int = Field(..., description="New buffer size"),
        ctx: Context = None
    ) -> dict:
        """Resize the circular buffer"""
        if new_size < 100 or new_size > 1000000:
            return {"success": False, "error": "Size must be between 100 and 1,000,000"}

        result = self.data_buffer.resize_buffer(new_size)
        return {"success": True, **result}
