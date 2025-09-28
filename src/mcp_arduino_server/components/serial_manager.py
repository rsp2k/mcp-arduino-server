"""
Serial Connection Manager for Arduino MCP Server
Handles serial port connections, monitoring, and communication
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import serial
import serial.tools.list_ports

try:
    import serial_asyncio
except ImportError:
    # Fall back to serial.aio if serial_asyncio not available
    try:
        from serial import aio as serial_asyncio
    except ImportError:
        # Create a dummy module for testing without serial
        class DummySerialAsyncio:
            async def create_serial_connection(*args, **kwargs):
                raise NotImplementedError("pyserial-asyncio not installed")
        serial_asyncio = DummySerialAsyncio()

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Serial connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    BUSY = "busy"  # Being used by another operation (e.g., upload)


@dataclass
class SerialPortInfo:
    """Information about a serial port"""
    device: str
    description: str
    hwid: str
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    interface: str | None = None

    @classmethod
    def from_list_ports_info(cls, info) -> "SerialPortInfo":
        """Create from serial.tools.list_ports.ListPortInfo"""
        return cls(
            device=info.device,
            description=info.description or "",
            hwid=info.hwid or "",
            vid=info.vid,
            pid=info.pid,
            serial_number=info.serial_number,
            location=info.location,
            manufacturer=info.manufacturer,
            product=info.product,
            interface=info.interface
        )

    def is_arduino_compatible(self) -> bool:
        """Check if this appears to be an Arduino-compatible device"""
        # Common Arduino VID/PIDs
        arduino_vids = [0x2341, 0x2a03, 0x1a86, 0x0403, 0x10c4]
        if self.vid in arduino_vids:
            return True

        # Check description/manufacturer
        arduino_keywords = ["arduino", "genuino", "esp32", "esp8266", "ch340", "ft232", "cp210"]
        check_str = f"{self.description} {self.manufacturer} {self.product}".lower()
        return any(keyword in check_str for keyword in arduino_keywords)


@dataclass
class SerialConnection:
    """Represents a serial connection"""
    port: str
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = 'N'
    stopbits: float = 1
    timeout: float | None = None
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False
    state: ConnectionState = ConnectionState.DISCONNECTED
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    serial_obj: serial.Serial | None = None
    info: SerialPortInfo | None = None
    last_activity: datetime | None = None
    error_message: str | None = None
    listeners: set[Callable] = field(default_factory=set)
    buffer: list[str] = field(default_factory=list)
    max_buffer_size: int = 1000

    async def readline(self) -> str | None:
        """Read a line from the serial port"""
        if self.reader and self.state == ConnectionState.CONNECTED:
            try:
                data = await self.reader.readline()
                line = data.decode('utf-8', errors='ignore').strip()
                self.last_activity = datetime.now()

                # Add to buffer
                self.buffer.append(f"[{datetime.now().isoformat()}] {line}")
                if len(self.buffer) > self.max_buffer_size:
                    self.buffer.pop(0)

                # Notify listeners
                for listener in self.listeners:
                    if asyncio.iscoroutinefunction(listener):
                        await listener(line)
                    else:
                        listener(line)

                return line
            except Exception as e:
                logger.error(f"Error reading from {self.port}: {e}")
                self.error_message = str(e)
                self.state = ConnectionState.ERROR
        return None

    async def write(self, data: str) -> bool:
        """Write data to the serial port"""
        if self.writer and self.state == ConnectionState.CONNECTED:
            try:
                self.writer.write(data.encode('utf-8'))
                await self.writer.drain()
                self.last_activity = datetime.now()
                return True
            except Exception as e:
                logger.error(f"Error writing to {self.port}: {e}")
                self.error_message = str(e)
                self.state = ConnectionState.ERROR
        return False

    async def writeline(self, line: str) -> bool:
        """Write a line to the serial port (adds newline if needed)"""
        if not line.endswith('\n'):
            line += '\n'
        return await self.write(line)

    def add_listener(self, callback: Callable) -> None:
        """Add a listener for incoming data"""
        self.listeners.add(callback)

    def remove_listener(self, callback: Callable) -> None:
        """Remove a listener"""
        self.listeners.discard(callback)

    def get_buffer_content(self, last_n_lines: int | None = None) -> list[str]:
        """Get buffered content"""
        if last_n_lines:
            return self.buffer[-last_n_lines:]
        return self.buffer.copy()

    def clear_buffer(self) -> None:
        """Clear the buffer"""
        self.buffer.clear()


class SerialConnectionManager:
    """Manages multiple serial connections with auto-reconnection and monitoring"""

    def __init__(self):
        self.connections: dict[str, SerialConnection] = {}
        self.monitoring_tasks: dict[str, asyncio.Task] = {}
        self.auto_reconnect: bool = True
        self.reconnect_delay: float = 2.0
        self._lock = asyncio.Lock()
        self._running = False
        self._discovery_task: asyncio.Task | None = None

    async def start(self):
        """Start the connection manager"""
        self._running = True
        # Start port discovery task
        self._discovery_task = asyncio.create_task(self._port_discovery_loop())
        logger.info("Serial Connection Manager started")

    async def stop(self):
        """Stop the connection manager and clean up"""
        self._running = False

        # Cancel discovery task
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass

        # Disconnect all ports
        for port in list(self.connections.keys()):
            await self.disconnect(port)

        logger.info("Serial Connection Manager stopped")

    async def list_ports(self) -> list[SerialPortInfo]:
        """List all available serial ports"""
        ports = []
        for port_info in serial.tools.list_ports.comports():
            ports.append(SerialPortInfo.from_list_ports_info(port_info))
        return ports

    async def list_arduino_ports(self) -> list[SerialPortInfo]:
        """List serial ports that appear to be Arduino-compatible"""
        all_ports = await self.list_ports()
        return [p for p in all_ports if p.is_arduino_compatible()]

    async def connect(
        self,
        port: str,
        baudrate: int = 115200,
        bytesize: int = 8,  # 5, 6, 7, or 8
        parity: str = 'N',  # 'N', 'E', 'O', 'M', 'S'
        stopbits: float = 1,  # 1, 1.5, or 2
        timeout: float | None = None,
        xonxoff: bool = False,  # Software flow control
        rtscts: bool = False,  # Hardware (RTS/CTS) flow control
        dsrdtr: bool = False,  # Hardware (DSR/DTR) flow control
        inter_byte_timeout: float | None = None,
        write_timeout: float | None = None,
        auto_monitor: bool = True,
        exclusive: bool = False
    ) -> SerialConnection:
        """
        Connect to a serial port with full configuration

        Args:
            port: Port name (e.g., '/dev/ttyUSB0' or 'COM3')
            baudrate: Baud rate (e.g., 9600, 115200, 921600)
            bytesize: Number of data bits (5, 6, 7, or 8)
            parity: Parity checking ('N'=None, 'E'=Even, 'O'=Odd, 'M'=Mark, 'S'=Space)
            stopbits: Number of stop bits (1, 1.5, or 2)
            timeout: Read timeout in seconds (None = blocking)
            xonxoff: Enable software flow control
            rtscts: Enable hardware (RTS/CTS) flow control
            dsrdtr: Enable hardware (DSR/DTR) flow control
            inter_byte_timeout: Inter-character timeout (None to disable)
            write_timeout: Write timeout in seconds (None = blocking)
            auto_monitor: Start monitoring automatically
            exclusive: If True, disconnect other connections first
        """
        async with self._lock:
            # If exclusive, disconnect all other ports
            if exclusive:
                for other_port in list(self.connections.keys()):
                    if other_port != port:
                        await self._disconnect_internal(other_port)

            # Check if already connected
            if port in self.connections:
                conn = self.connections[port]
                if conn.state == ConnectionState.CONNECTED:
                    return conn
                # Try to reconnect
                await self._disconnect_internal(port)

            # Get port info
            port_info = None
            for info in await self.list_ports():
                if info.device == port:
                    port_info = info
                    break

            # Create connection with all parameters
            conn = SerialConnection(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=timeout,
                xonxoff=xonxoff,
                rtscts=rtscts,
                dsrdtr=dsrdtr,
                info=port_info,
                state=ConnectionState.CONNECTING
            )

            try:
                # Create async serial connection with all parameters
                reader, writer = await serial_asyncio.open_serial_connection(
                    url=port,
                    baudrate=baudrate,
                    bytesize=bytesize,
                    parity=parity,
                    stopbits=stopbits,
                    timeout=timeout,
                    xonxoff=xonxoff,
                    rtscts=rtscts,
                    dsrdtr=dsrdtr,
                    inter_byte_timeout=inter_byte_timeout,
                    write_timeout=write_timeout
                )

                conn.reader = reader
                conn.writer = writer
                conn.state = ConnectionState.CONNECTED
                conn.last_activity = datetime.now()

                self.connections[port] = conn

                # Start monitoring if requested
                if auto_monitor:
                    await self.start_monitoring(port)

                logger.info(f"Connected to {port} at {baudrate} baud")
                return conn

            except Exception as e:
                logger.error(f"Failed to connect to {port}: {e}")
                conn.state = ConnectionState.ERROR
                conn.error_message = str(e)
                raise

    async def disconnect(self, port: str) -> bool:
        """Disconnect from a serial port"""
        async with self._lock:
            return await self._disconnect_internal(port)

    async def _disconnect_internal(self, port: str) -> bool:
        """Internal disconnect (assumes lock is held)"""
        if port not in self.connections:
            return False

        # Stop monitoring
        if port in self.monitoring_tasks:
            self.monitoring_tasks[port].cancel()
            try:
                await self.monitoring_tasks[port]
            except asyncio.CancelledError:
                pass
            del self.monitoring_tasks[port]

        # Close connection
        conn = self.connections[port]
        if conn.writer:
            conn.writer.close()
            await conn.writer.wait_closed()

        conn.state = ConnectionState.DISCONNECTED
        del self.connections[port]

        logger.info(f"Disconnected from {port}")
        return True

    async def start_monitoring(self, port: str) -> bool:
        """Start monitoring a serial port for incoming data"""
        if port not in self.connections:
            return False

        if port in self.monitoring_tasks:
            return True  # Already monitoring

        task = asyncio.create_task(self._monitor_port(port))
        self.monitoring_tasks[port] = task
        return True

    async def stop_monitoring(self, port: str) -> bool:
        """Stop monitoring a serial port"""
        if port in self.monitoring_tasks:
            self.monitoring_tasks[port].cancel()
            try:
                await self.monitoring_tasks[port]
            except asyncio.CancelledError:
                pass
            del self.monitoring_tasks[port]
            return True
        return False

    async def _monitor_port(self, port: str):
        """Monitor a port for incoming data"""
        conn = self.connections.get(port)
        if not conn:
            return

        logger.info(f"Starting monitor for {port}")

        while conn.state == ConnectionState.CONNECTED and self._running:
            try:
                line = await conn.readline()
                if line is not None:
                    # Data is handled by readline and listeners
                    pass
                else:
                    # Connection might be closed
                    if self.auto_reconnect:
                        logger.info(f"Connection to {port} lost, attempting reconnect...")
                        await asyncio.sleep(self.reconnect_delay)
                        try:
                            await self.connect(port, conn.baudrate, auto_monitor=False)
                        except Exception as e:
                            logger.error(f"Reconnection failed: {e}")
                    else:
                        break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error for {port}: {e}")
                if self.auto_reconnect:
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    break

        logger.info(f"Stopped monitoring {port}")

    async def _port_discovery_loop(self):
        """Periodically discover new/removed ports"""
        known_ports = set()

        while self._running:
            try:
                current_ports = set()
                for port_info in serial.tools.list_ports.comports():
                    current_ports.add(port_info.device)

                # Detect new ports
                new_ports = current_ports - known_ports
                if new_ports:
                    logger.info(f"New serial ports detected: {new_ports}")
                    # Could emit an event or callback here

                # Detect removed ports
                removed_ports = known_ports - current_ports
                if removed_ports:
                    logger.info(f"Serial ports removed: {removed_ports}")
                    # Auto-cleanup disconnected ports
                    for port in removed_ports:
                        if port in self.connections:
                            conn = self.connections[port]
                            if conn.state != ConnectionState.BUSY:
                                await self.disconnect(port)

                known_ports = current_ports

            except Exception as e:
                logger.error(f"Port discovery error: {e}")

            await asyncio.sleep(2.0)  # Check every 2 seconds

    def get_connection(self, port: str) -> SerialConnection | None:
        """Get a connection by port name"""
        return self.connections.get(port)

    def get_connected_ports(self) -> list[str]:
        """Get list of connected ports"""
        return [
            port for port, conn in self.connections.items()
            if conn.state == ConnectionState.CONNECTED
        ]

    async def send_command(self, port: str, command: str, wait_for_response: bool = True, timeout: float = 5.0) -> str | None:
        """
        Send a command to a port and optionally wait for response

        Args:
            port: Port to send command to
            command: Command to send
            wait_for_response: Whether to wait for a response
            timeout: Timeout for response
        """
        conn = self.get_connection(port)
        if not conn or conn.state != ConnectionState.CONNECTED:
            return None

        # Send command
        if not await conn.writeline(command):
            return None

        if not wait_for_response:
            return ""

        # Wait for response
        response_lines = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            line = await asyncio.wait_for(conn.readline(), timeout=0.1)
            if line:
                response_lines.append(line)
                # Check for common end markers
                if any(marker in line.lower() for marker in ["ok", "error", "done", "ready"]):
                    break
            else:
                await asyncio.sleep(0.01)

        return "\n".join(response_lines) if response_lines else None

    async def reset_board(self, port: str, method: str = "dtr") -> bool:
        """
        Reset an Arduino board

        Args:
            port: Port the board is connected to
            method: Reset method ('dtr', 'rts', or '1200bps')
        """
        try:
            if method == "1200bps":
                # Touch at 1200bps for boards like Leonardo
                temp_ser = serial.Serial(port, 1200)
                temp_ser.close()
                await asyncio.sleep(0.5)
                return True
            else:
                # Use DTR/RTS for reset
                temp_ser = serial.Serial(port, 115200)
                if method == "dtr":
                    temp_ser.dtr = False
                    await asyncio.sleep(0.1)
                    temp_ser.dtr = True
                elif method == "rts":
                    temp_ser.rts = False
                    await asyncio.sleep(0.1)
                    temp_ser.rts = True
                temp_ser.close()
                await asyncio.sleep(0.5)
                return True
        except Exception as e:
            logger.error(f"Failed to reset board on {port}: {e}")
            return False

    def set_port_busy(self, port: str, busy: bool = True):
        """Mark a port as busy (e.g., during upload)"""
        conn = self.get_connection(port)
        if conn:
            conn.state = ConnectionState.BUSY if busy else ConnectionState.CONNECTED
