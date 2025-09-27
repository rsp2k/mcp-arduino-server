# 🚀 Quick Start Guide

> Get up and running with MCP Arduino Server in 5 minutes!

## Prerequisites

- Python 3.9+
- Arduino CLI installed
- An Arduino or ESP32 board
- USB cable

## 1️⃣ Installation

```bash
# Using uv (recommended)
uv pip install mcp-arduino-server

# Or using pip
pip install mcp-arduino-server
```

## 2️⃣ Configuration

### For Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arduino": {
      "command": "uv",
      "args": ["run", "mcp-arduino-server"],
      "env": {
        "ARDUINO_SKETCHES_DIR": "~/Documents/Arduino_MCP_Sketches"
      }
    }
  }
}
```

### For Other MCP Clients

Create a `.env` file:

```bash
# Required
ARDUINO_SKETCHES_DIR=~/Documents/Arduino_MCP_Sketches

# Optional (with defaults)
ARDUINO_SERIAL_BUFFER_SIZE=10000
LOG_LEVEL=INFO
```

## 3️⃣ First Sketch

### Create and Upload

```python
# Create a new sketch
await arduino_create_sketch(sketch_name="Blink")

# Write the code
await arduino_write_sketch(
    sketch_name="Blink",
    content="""
void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  Serial.println("Blink sketch started!");
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.println("LED ON");
  delay(1000);

  digitalWrite(LED_BUILTIN, LOW);
  Serial.println("LED OFF");
  delay(1000);
}
"""
)

# Find your board
boards = await arduino_list_boards()
# Returns: [{"port": "/dev/ttyUSB0", "fqbn": "arduino:avr:uno", ...}]

# Upload to board
await arduino_upload_sketch(
    sketch_name="Blink",
    port="/dev/ttyUSB0"
)
```

## 4️⃣ Serial Monitoring

### Connect and Monitor

```python
# Connect to serial port
await serial_connect(
    port="/dev/ttyUSB0",
    baudrate=115200
)

# Read serial data
data = await serial_read(
    port="/dev/ttyUSB0",
    create_cursor=True
)
# Returns data with cursor for pagination

# Send commands
await serial_send(
    port="/dev/ttyUSB0",
    data="HELLO"
)
```

## 5️⃣ ESP32 Setup (Optional)

### Install ESP32 Support

```python
# One-time setup
await arduino_install_esp32()

# List ESP32 boards
boards = await arduino_list_boards()
# Now includes ESP32 boards
```

### ESP32 Example

```python
# Create ESP32 sketch
await arduino_write_sketch(
    sketch_name="ESP32_WiFi",
    content="""
#include <WiFi.h>

void setup() {
  Serial.begin(115200);
  Serial.println("ESP32 Started!");

  // Print chip info
  Serial.print("Chip Model: ");
  Serial.println(ESP.getChipModel());
  Serial.print("Chip Cores: ");
  Serial.println(ESP.getChipCores());
}

void loop() {
  Serial.print("Free Heap: ");
  Serial.println(ESP.getFreeHeap());
  delay(5000);
}
"""
)

# Upload to ESP32
await arduino_upload_sketch(
    sketch_name="ESP32_WiFi",
    port="/dev/ttyUSB0",
    board_fqbn="esp32:esp32:esp32"
)
```

## 🎯 Common Tasks

### List Available Ports

```python
ports = await serial_list_ports(arduino_only=True)
# Returns Arduino-compatible ports only
```

### Install Libraries

```python
# Search for libraries
libraries = await arduino_search_libraries(query="servo")

# Install a library
await arduino_install_library(library_name="Servo")
```

### Monitor with Cursor

```python
# Create cursor for continuous reading
result = await serial_read(create_cursor=True)
cursor_id = result['cursor_id']

# Read next batch
while True:
    data = await serial_read(
        cursor_id=cursor_id,
        limit=10
    )
    for entry in data['entries']:
        print(f"{entry['timestamp']}: {entry['data']}")

    if not data['has_more']:
        break
```

### Generate Circuit Diagram

```python
# From description (uses AI)
await wireviz_generate_from_description(
    description="Arduino Uno connected to LED on pin 13 with 220 ohm resistor"
)

# From YAML
await wireviz_generate_from_yaml(
    yaml_content="""
connectors:
  Arduino:
    type: Arduino Uno
    pins: [GND, 13]
  LED:
    type: LED
    pins: [cathode, anode]

cables:
  power:
    connections:
      - Arduino: [13]
      - LED: [anode]
  ground:
    connections:
      - Arduino: [GND]
      - LED: [cathode]
"""
)
```

## ⚡ Pro Tips

1. **Auto-compile on write**: Sketches are automatically compiled when written
2. **Buffer management**: Adjust `ARDUINO_SERIAL_BUFFER_SIZE` for your data rate
3. **Exclusive mode**: Use `exclusive=True` when connecting to avoid conflicts
4. **Auto-reconnect**: Serial connections auto-reconnect on disconnect
5. **Cursor recovery**: Enable `auto_recover=True` for robust reading

## 🔍 Next Steps

- **[Serial Integration Guide](./SERIAL_INTEGRATION_GUIDE.md)** - Advanced serial features
- **[API Reference](./SERIAL_MONITOR.md)** - Complete tool documentation
- **[ESP32 Guide](./ESP32_GUIDE.md)** - ESP32-specific features
- **[Examples](./EXAMPLES.md)** - More code samples

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| "Port not found" | Check USB connection and drivers |
| "Permission denied" | Linux/Mac: Add user to `dialout` group |
| "Board not detected" | Install board core via `arduino_install_core()` |
| "Upload failed" | Check correct port and board selection |
| "Missing libraries" | Use `arduino_install_library()` |

## 💬 Getting Help

- Check [Documentation Index](./README.md)
- Review [Common Issues](./SERIAL_INTEGRATION_GUIDE.md#common-issues--solutions)
- Visit [GitHub Issues](https://github.com/evolutis/mcp-arduino-server)

---

*Ready to build something amazing? You're all set! 🎉*