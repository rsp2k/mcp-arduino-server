# 📡 Arduino Serial Monitor Documentation

## Overview

The Arduino MCP Server includes a professional-grade serial monitoring system with cursor-based data streaming, FastMCP state management, and real-time communication capabilities. This enables seamless interaction with Arduino and ESP32 boards through the Model Context Protocol.

## ✨ Features

- **🔌 Multiple Connections**: Manage multiple serial ports simultaneously
- **🔄 Auto-Reconnection**: Automatic reconnection on disconnect
- **📊 Cursor-Based Pagination**: Efficient streaming of large data volumes
- **💾 State Persistence**: Connections tracked across MCP requests
- **🎯 Smart Filtering**: Filter by port, data type, or custom patterns
- **🔍 Auto-Detection**: Identifies Arduino-compatible devices automatically
- **⚡ Async Architecture**: Non-blocking I/O for responsive monitoring

## 🛠️ Architecture

### Components

```
┌─────────────────────────────────────────────┐
│             FastMCP Server                   │
├─────────────────────────────────────────────┤
│          ArduinoSerial (MCPMixin)            │
├──────────────────┬──────────────────────────┤
│  SerialManager   │    SerialDataBuffer      │
├──────────────────┴──────────────────────────┤
│            pyserial-asyncio                  │
└─────────────────────────────────────────────┘
```

### Key Classes

1. **`ArduinoSerial`** - Main component using MCPMixin pattern
2. **`SerialConnectionManager`** - Handles connections and auto-discovery
3. **`SerialDataBuffer`** - Circular buffer with cursor support
4. **`SerialConnection`** - Individual connection state and I/O

## 📚 API Reference

### Tools

#### `serial_connect`
Connect to a serial port with automatic monitoring.

**Parameters:**
- `port` (str, required): Serial port path (e.g., `/dev/ttyUSB0`, `COM3`)
- `baudrate` (int, default: 115200): Communication speed
- `auto_monitor` (bool, default: true): Start monitoring automatically
- `exclusive` (bool, default: false): Disconnect other ports first

**Example:**
```json
{
  "tool": "serial_connect",
  "parameters": {
    "port": "/dev/ttyUSB0",
    "baudrate": 115200,
    "auto_monitor": true
  }
}
```

#### `serial_disconnect`
Disconnect from a serial port.

**Parameters:**
- `port` (str, required): Port to disconnect

#### `serial_send`
Send data to a connected serial port.

**Parameters:**
- `port` (str, required): Target port
- `data` (str, required): Data to send
- `add_newline` (bool, default: true): Append newline
- `wait_response` (bool, default: false): Wait for response
- `timeout` (float, default: 5.0): Response timeout in seconds

**Example:**
```json
{
  "tool": "serial_send",
  "parameters": {
    "port": "/dev/ttyUSB0",
    "data": "AT+RST",
    "wait_response": true,
    "timeout": 3.0
  }
}
```

#### `serial_read`
Read serial data with cursor-based pagination.

**Parameters:**
- `cursor_id` (str, optional): Cursor for pagination
- `port` (str, optional): Filter by port
- `limit` (int, default: 100): Maximum entries to return
- `type_filter` (str, optional): Filter by type (received/sent/system/error)
- `create_cursor` (bool, default: false): Create new cursor if not provided

**Example:**
```json
{
  "tool": "serial_read",
  "parameters": {
    "port": "/dev/ttyUSB0",
    "limit": 50,
    "create_cursor": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "cursor_id": "uuid-here",
  "has_more": true,
  "entries": [
    {
      "timestamp": "2025-09-27T02:45:18.795233",
      "type": "received",
      "data": "System Status Report",
      "port": "/dev/ttyUSB0",
      "index": 1
    }
  ],
  "count": 50
}
```

#### `serial_list_ports`
List available serial ports.

**Parameters:**
- `arduino_only` (bool, default: false): List only Arduino-compatible ports

**Response:**
```json
{
  "success": true,
  "ports": [
    {
      "device": "/dev/ttyUSB0",
      "description": "USB Serial",
      "vid": 6790,
      "pid": 29987,
      "is_arduino": true
    }
  ]
}
```

#### `serial_clear_buffer`
Clear serial data buffer.

**Parameters:**
- `port` (str, optional): Clear specific port or all if None

#### `serial_reset_board`
Reset an Arduino board using various methods.

**Parameters:**
- `port` (str, required): Serial port of the board
- `method` (str, default: "dtr"): Reset method (dtr/rts/1200bps)

#### `serial_monitor_state`
Get current state of serial monitor.

**Response:**
```json
{
  "initialized": true,
  "connected_ports": ["/dev/ttyUSB0"],
  "active_monitors": [],
  "buffer_size": 272,
  "active_cursors": 1,
  "connections": {
    "/dev/ttyUSB0": {
      "state": "connected",
      "baudrate": 115200,
      "last_activity": "2025-09-27T02:46:45.950224",
      "error": null
    }
  }
}
```

## 🚀 Usage Examples

### Basic Connection and Monitoring

```python
# 1. List available ports
ports = await serial_list_ports(arduino_only=True)

# 2. Connect to first Arduino port
if ports['ports']:
    port = ports['ports'][0]['device']
    await serial_connect(port=port, baudrate=115200)

    # 3. Read incoming data with cursor
    result = await serial_read(
        port=port,
        limit=50,
        create_cursor=True
    )

    cursor_id = result['cursor_id']

    # 4. Continue reading from cursor
    while result['has_more']:
        result = await serial_read(
            cursor_id=cursor_id,
            limit=50
        )
        process_data(result['entries'])
```

### ESP32 Boot Sequence Capture

```python
# Reset ESP32 and capture boot sequence
await serial_reset_board(port="/dev/ttyUSB0", method="dtr")

# Wait briefly for reset
await asyncio.sleep(0.5)

# Read boot data
boot_data = await serial_read(
    port="/dev/ttyUSB0",
    limit=100,
    create_cursor=True
)

# Parse boot information
for entry in boot_data['entries']:
    if entry['type'] == 'received':
        if 'ESP32' in entry['data']:
            print(f"ESP32 detected: {entry['data']}")
```

### Interactive Commands

```python
# Send AT command and wait for response
response = await serial_send(
    port="/dev/ttyUSB0",
    data="AT+GMR",  # Get firmware version
    wait_response=True,
    timeout=3.0
)

if response['success']:
    print(f"Firmware: {response['response']}")
```

### Monitoring Multiple Ports

```python
# Connect to multiple devices
ports = ["/dev/ttyUSB0", "/dev/ttyUSB1"]
for port in ports:
    await serial_connect(port=port, baudrate=115200)

# Read from all ports
state = await serial_monitor_state()
for port in state['connected_ports']:
    data = await serial_read(port=port, limit=10)
    print(f"{port}: {data['count']} entries")
```

## 🔧 Data Types

### SerialDataType Enum
- `RECEIVED`: Data received from the device
- `SENT`: Data sent to the device
- `SYSTEM`: System messages (connected/disconnected)
- `ERROR`: Error messages

### SerialDataEntry Structure
```python
{
    "timestamp": "ISO-8601 timestamp",
    "type": "received|sent|system|error",
    "data": "actual data string",
    "port": "/dev/ttyUSB0",
    "index": 123  # Global incrementing index
}
```

## 🎯 Best Practices

### 1. Cursor Management
- Create a cursor for long-running sessions
- Store cursor_id for continuous reading
- Delete cursors when done to free memory

### 2. Buffer Management
- Default buffer size: 10,000 entries
- Clear buffer periodically for long sessions
- Use type filters to reduce data volume

### 3. Connection Handling
- Check `serial_monitor_state` before operations
- Use `exclusive` mode for critical operations
- Handle reconnection gracefully

### 4. Performance Optimization
- Use appropriate `limit` values (50-100 recommended)
- Filter by type when looking for specific data
- Use `wait_response=false` for fire-and-forget commands

## 🔌 Hardware Compatibility

### Tested Devices
- ✅ ESP32 (ESP32-D0WD-V3)
- ✅ ESP8266
- ✅ Arduino Uno
- ✅ Arduino Nano
- ✅ Arduino Mega
- ✅ STM32 with Arduino bootloader

### Baud Rates
- Standard: 9600, 19200, 38400, 57600, 115200, 230400
- ESP32 default: 115200
- Arduino default: 9600

### Reset Methods
- **DTR**: Most common for Arduino boards
- **RTS**: Alternative reset method
- **1200bps**: Special for Leonardo, Micro, Yún

## 🐛 Troubleshooting

### Connection Issues
```bash
# Check port permissions
ls -l /dev/ttyUSB0

# Add user to dialout group (Linux)
sudo usermod -a -G dialout $USER

# List USB devices
lsusb
```

### Buffer Overflow
```python
# Clear buffer if getting too large
await serial_clear_buffer(port="/dev/ttyUSB0")

# Check buffer size
state = await serial_monitor_state()
print(f"Buffer size: {state['buffer_size']}")
```

### Missing Data
```python
# Ensure monitoring is active
state = await serial_monitor_state()
if port not in state['connected_ports']:
    await serial_connect(port=port, auto_monitor=True)
```

## 📈 Performance Metrics

- **Connection Time**: < 100ms typical
- **Data Latency**: < 10ms from device to buffer
- **Cursor Read**: O(n) where n = limit
- **Buffer Insert**: O(1) amortized
- **Max Throughput**: 1MB/s+ (baudrate limited)

## 🔒 State Management

The serial monitor integrates with FastMCP's context system:

```python
# State is preserved across tool calls
ctx.state["serial_monitor"] = SerialMonitorContext()

# Connections persist between requests
# Buffers maintain history
# Cursors track reading position
```

## 🎉 Advanced Features

### Custom Listeners
```python
# Add callback for incoming data
async def on_data(line: str):
    if "ERROR" in line:
        alert_user(line)

connection.add_listener(on_data)
```

### Pattern Matching
```python
# Read only error messages
errors = await serial_read(
    port=port,
    type_filter="error",
    limit=100
)
```

### Batch Operations
```python
# Disconnect all ports
state = await serial_monitor_state()
for port in state['connected_ports']:
    await serial_disconnect(port=port)
```

## 📝 License

Part of the Arduino MCP Server project. MIT Licensed.

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

## 🔗 Related Documentation

- [Arduino MCP Server README](../README.md)
- [FastMCP Documentation](https://docs.fastmcp.com)
- [pyserial Documentation](https://pyserial.readthedocs.io)