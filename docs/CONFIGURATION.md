# ⚙️ Configuration Guide

> Complete configuration reference for MCP Arduino Server

## 📋 Environment Variables

### Required Variables

#### `ARDUINO_SKETCHES_DIR`
- **Description**: Directory where Arduino sketches are stored
- **Default**: None (required)
- **Example**: `~/Documents/Arduino_MCP_Sketches`

```bash
export ARDUINO_SKETCHES_DIR="$HOME/Documents/Arduino_MCP_Sketches"
```

### Optional Variables

#### `ARDUINO_SERIAL_BUFFER_SIZE`
- **Description**: Maximum entries in circular buffer for serial data
- **Default**: `10000`
- **Range**: `100` to `1000000`
- **Guidance**:
  - Small systems: `1000` (minimal memory usage)
  - Normal use: `10000` (balanced performance)
  - High-speed logging: `100000` (captures more before wraparound)
  - Data analysis: `1000000` (maximum retention)

```bash
export ARDUINO_SERIAL_BUFFER_SIZE=50000  # For high-speed data
```

#### `ARDUINO_CLI_PATH`
- **Description**: Path to Arduino CLI executable
- **Default**: `/usr/local/bin/arduino-cli`
- **Auto-detection**: System PATH is searched if not set

```bash
export ARDUINO_CLI_PATH=/opt/arduino/arduino-cli
```

#### `WIREVIZ_PATH`
- **Description**: Path to WireViz executable for circuit diagrams
- **Default**: `/usr/local/bin/wireviz`
- **Required for**: Circuit diagram generation

```bash
export WIREVIZ_PATH=/usr/local/bin/wireviz
```

#### `ENABLE_CLIENT_SAMPLING`
- **Description**: Enable AI features using client-side LLM
- **Default**: `true`
- **Values**: `true` or `false`
- **Note**: No API keys required when enabled

```bash
export ENABLE_CLIENT_SAMPLING=true
```

#### `LOG_LEVEL`
- **Description**: Logging verbosity
- **Default**: `INFO`
- **Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

```bash
export LOG_LEVEL=DEBUG  # For troubleshooting
```

## 🔧 Configuration Methods

### Method 1: Environment File (.env)

Create a `.env` file in your project directory:

```bash
# .env file
ARDUINO_SKETCHES_DIR=~/Documents/Arduino_MCP_Sketches
ARDUINO_SERIAL_BUFFER_SIZE=10000
ARDUINO_CLI_PATH=/usr/local/bin/arduino-cli
WIREVIZ_PATH=/usr/local/bin/wireviz
ENABLE_CLIENT_SAMPLING=true
LOG_LEVEL=INFO
```

### Method 2: Claude Desktop Config

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "arduino": {
      "command": "uv",
      "args": ["run", "mcp-arduino-server"],
      "env": {
        "ARDUINO_SKETCHES_DIR": "~/Documents/Arduino_MCP_Sketches",
        "ARDUINO_SERIAL_BUFFER_SIZE": "10000",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Method 3: Shell Export

Set in your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
# Arduino MCP Server
export ARDUINO_SKETCHES_DIR="$HOME/Documents/Arduino_MCP_Sketches"
export ARDUINO_SERIAL_BUFFER_SIZE=10000
export LOG_LEVEL=INFO
```

### Method 4: Docker Compose

Using environment variables in `docker-compose.yml`:

```yaml
services:
  arduino-mcp:
    image: mcp-arduino-server
    environment:
      - ARDUINO_SKETCHES_DIR=/sketches
      - ARDUINO_SERIAL_BUFFER_SIZE=50000
      - LOG_LEVEL=DEBUG
    volumes:
      - ./sketches:/sketches
      - /dev:/dev  # For serial port access
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
    privileged: true  # Required for device access
```

## 🔑 Permissions

### Linux

Add user to `dialout` group for serial port access:

```bash
sudo usermod -a -G dialout $USER
# Logout and login for changes to take effect
```

### macOS

No special permissions needed for USB serial devices.

### Windows

Install appropriate USB drivers for your Arduino board.

## 📁 Directory Structure

The server expects this structure:

```
$ARDUINO_SKETCHES_DIR/
├── MySketch/
│   ├── MySketch.ino
│   └── data/           # Optional SPIFFS/LittleFS data
├── ESP32_Project/
│   ├── ESP32_Project.ino
│   ├── config.h
│   └── wifi_credentials.h
└── libraries/          # Local libraries (optional)
```

## 🎯 Configuration Profiles

### Development Profile

```bash
# .env.development
ARDUINO_SKETCHES_DIR=~/Arduino/dev_sketches
ARDUINO_SERIAL_BUFFER_SIZE=100000
LOG_LEVEL=DEBUG
ENABLE_CLIENT_SAMPLING=true
```

### Production Profile

```bash
# .env.production
ARDUINO_SKETCHES_DIR=/var/arduino/sketches
ARDUINO_SERIAL_BUFFER_SIZE=10000
LOG_LEVEL=WARNING
ENABLE_CLIENT_SAMPLING=true
```

### Memory-Constrained Profile

```bash
# .env.embedded
ARDUINO_SKETCHES_DIR=/tmp/sketches
ARDUINO_SERIAL_BUFFER_SIZE=1000  # Minimal buffer
LOG_LEVEL=ERROR
ENABLE_CLIENT_SAMPLING=false
```

## 🔍 Configuration Validation

Check your configuration:

```python
# Test configuration
import os

print("Configuration Check:")
print(f"Sketches Dir: {os.getenv('ARDUINO_SKETCHES_DIR', 'NOT SET')}")
print(f"Buffer Size: {os.getenv('ARDUINO_SERIAL_BUFFER_SIZE', '10000')}")
print(f"Log Level: {os.getenv('LOG_LEVEL', 'INFO')}")

# Verify directories exist
sketches_dir = os.path.expanduser(os.getenv('ARDUINO_SKETCHES_DIR', ''))
if os.path.exists(sketches_dir):
    print(f"✓ Sketches directory exists: {sketches_dir}")
else:
    print(f"✗ Sketches directory not found: {sketches_dir}")
```

## 🐳 Docker Configuration

### Dockerfile with Configuration

```dockerfile
FROM python:3.11-slim

# Install Arduino CLI
RUN apt-get update && apt-get install -y \
    wget \
    && wget https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Linux_64bit.tar.gz \
    && tar -xzf arduino-cli_latest_Linux_64bit.tar.gz -C /usr/local/bin \
    && rm arduino-cli_latest_Linux_64bit.tar.gz

# Install MCP Arduino Server
RUN pip install mcp-arduino-server

# Set default environment variables
ENV ARDUINO_SKETCHES_DIR=/sketches
ENV ARDUINO_SERIAL_BUFFER_SIZE=10000
ENV LOG_LEVEL=INFO

# Create sketches directory
RUN mkdir -p /sketches

# Run server
CMD ["mcp-arduino-server"]
```

### Docker Run Command

```bash
docker run -it \
  -e ARDUINO_SKETCHES_DIR=/sketches \
  -e ARDUINO_SERIAL_BUFFER_SIZE=50000 \
  -v $(pwd)/sketches:/sketches \
  --device /dev/ttyUSB0 \
  --privileged \
  mcp-arduino-server
```

## 🔧 Advanced Configuration

### Custom Arduino CLI Config

Create `~/.arduino15/arduino-cli.yaml`:

```yaml
board_manager:
  additional_urls:
    - https://arduino.esp8266.com/stable/package_esp8266com_index.json
    - https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json

daemon:
  port: "50051"

directories:
  data: ~/.arduino15
  downloads: ~/.arduino15/staging
  user: ~/Arduino

library:
  enable_unsafe_install: false

logging:
  level: info
  format: text
```

### Serial Port Aliases (Linux)

Create consistent device names using udev rules:

```bash
# /etc/udev/rules.d/99-arduino.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", ATTRS{idProduct}=="0043", SYMLINK+="arduino_uno"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="arduino_nano"
```

Then use: `/dev/arduino_uno` instead of `/dev/ttyUSB0`

## 🆘 Troubleshooting Configuration

### Issue: "ARDUINO_SKETCHES_DIR not set"

**Solution**: Set the required environment variable:
```bash
export ARDUINO_SKETCHES_DIR="$HOME/Documents/Arduino_MCP_Sketches"
```

### Issue: "Permission denied on /dev/ttyUSB0"

**Solution** (Linux):
```bash
sudo usermod -a -G dialout $USER
# Then logout and login
```

### Issue: "Buffer overflow - missing data"

**Solution**: Increase buffer size:
```bash
export ARDUINO_SERIAL_BUFFER_SIZE=100000
```

### Issue: "arduino-cli not found"

**Solution**: Install Arduino CLI:
```bash
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
```

## 📊 Performance Tuning

### Buffer Size Guidelines

| Data Rate | Buffer Size | Memory Usage | Use Case |
|-----------|------------|--------------|----------|
| < 10 Hz | 1,000 | ~100 KB | Basic debugging |
| < 100 Hz | 10,000 | ~1 MB | Normal operation |
| < 1 kHz | 100,000 | ~10 MB | High-speed logging |
| Any | 1,000,000 | ~100 MB | Long-term analysis |

### Memory Calculation

```python
# Estimate memory usage
buffer_size = int(os.getenv('ARDUINO_SERIAL_BUFFER_SIZE', '10000'))
bytes_per_entry = 100  # Approximate
memory_mb = (buffer_size * bytes_per_entry) / (1024 * 1024)
print(f"Estimated memory usage: {memory_mb:.1f} MB")
```

## 🔐 Security Considerations

1. **Sketches Directory**: Ensure proper permissions on sketches directory
2. **Serial Ports**: Limit device access to trusted USB devices
3. **Client Sampling**: Disable if not using AI features to reduce attack surface
4. **Docker**: Avoid `--privileged` if possible; use specific device mappings

## 📝 Example Configuration Files

Complete `.env.example` is provided in the repository:
```bash
cp .env.example .env
# Edit .env with your settings
```

---

*For more help, see [Troubleshooting Guide](./TROUBLESHOOTING.md) or [Quick Start](./QUICK_START.md)*