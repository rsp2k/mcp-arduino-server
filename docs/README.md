# 📚 MCP Arduino Server Documentation

> Complete documentation for the Model Context Protocol (MCP) Arduino Server

## 🚀 Quick Links

| Document | Description |
|----------|-------------|
| **[Quick Start Guide](./QUICK_START.md)** | Get up and running in 5 minutes |
| **[Serial Monitor Guide](./SERIAL_INTEGRATION_GUIDE.md)** | Complete serial monitoring tutorial |
| **[API Reference](./SERIAL_MONITOR.md)** | Detailed API documentation |
| **[Architecture](./CIRCULAR_BUFFER_ARCHITECTURE.md)** | Circular buffer technical details |

## 📖 Documentation Structure

### 🎯 Getting Started
- **[Quick Start Guide](./QUICK_START.md)** - Installation and first sketch
- **[Configuration Guide](./CONFIGURATION.md)** - Environment variables and settings
- **[Examples](./EXAMPLES.md)** - Sample code and common patterns

### 🔧 How-To Guides
- **[Serial Integration Guide](./SERIAL_INTEGRATION_GUIDE.md)** - Step-by-step serial monitoring
- **[ESP32 Development](./ESP32_GUIDE.md)** - ESP32-specific workflows
- **[Debugging Guide](./DEBUGGING_GUIDE.md)** - Using debug tools effectively

### 📘 Reference
- **[Serial Monitor API](./SERIAL_MONITOR.md)** - Complete tool reference
- **[Arduino Tools API](./ARDUINO_TOOLS_API.md)** - Sketch and library management
- **[WireViz API](./WIREVIZ_API.md)** - Circuit diagram generation

### 🏗️ Architecture
- **[Circular Buffer Architecture](./CIRCULAR_BUFFER_ARCHITECTURE.md)** - Memory management design
- **[System Architecture](./ARCHITECTURE.md)** - Overall system design
- **[MCP Integration](./MCP_INTEGRATION.md)** - How MCP protocol is used

## 🎓 By Use Case

### For Arduino Developers
1. Start with **[Quick Start Guide](./QUICK_START.md)**
2. Learn serial monitoring with **[Serial Integration Guide](./SERIAL_INTEGRATION_GUIDE.md)**
3. Reference **[Serial Monitor API](./SERIAL_MONITOR.md)** for specific tools

### For ESP32 Developers
1. Install ESP32 support: **[ESP32 Guide](./ESP32_GUIDE.md)**
2. Use high-speed serial: **[Serial Integration Guide](./SERIAL_INTEGRATION_GUIDE.md#esp32-development-workflow)**
3. Debug with dual-core support: **[Debugging Guide](./DEBUGGING_GUIDE.md#esp32-debugging)**

### For System Integrators
1. Understand **[Architecture](./ARCHITECTURE.md)**
2. Configure via **[Configuration Guide](./CONFIGURATION.md)**
3. Review **[Circular Buffer Architecture](./CIRCULAR_BUFFER_ARCHITECTURE.md)** for scaling

## 🔍 Features by Category

### 📡 Serial Communication
- Real-time monitoring with cursor-based streaming
- Full parameter control (baudrate, parity, flow control)
- Circular buffer with automatic memory management
- Multiple concurrent readers support
- Auto-reconnection and error recovery

### 🎛️ Arduino Management
- Sketch creation, compilation, and upload
- Board detection and management
- Library installation and search
- ESP32 and Arduino board support

### 🔌 Circuit Design
- WireViz diagram generation from natural language
- YAML-based circuit definitions
- Automatic component detection

### 🐛 Debugging
- GDB integration for hardware debugging
- Breakpoint management
- Memory inspection
- Interactive and automated modes

## 📊 Performance & Scaling

| Scenario | Buffer Size | Data Rate | Memory Usage |
|----------|------------|-----------|--------------|
| Basic Debugging | 1,000 | < 10 Hz | ~100 KB |
| Normal Monitoring | 10,000 | < 100 Hz | ~1 MB |
| High-Speed Logging | 100,000 | < 1 kHz | ~10 MB |
| Data Analysis | 1,000,000 | Any | ~100 MB |

## 🔧 Configuration Reference

### Essential Environment Variables

```bash
# Required
ARDUINO_SKETCHES_DIR=~/Documents/Arduino_MCP_Sketches

# Serial Monitor
ARDUINO_SERIAL_BUFFER_SIZE=10000  # Buffer size (100-1000000)

# Optional
ARDUINO_CLI_PATH=/usr/local/bin/arduino-cli
WIREVIZ_PATH=/usr/local/bin/wireviz
LOG_LEVEL=INFO
ENABLE_CLIENT_SAMPLING=true
```

## 🆘 Troubleshooting Quick Reference

| Issue | Solution | Documentation |
|-------|----------|---------------|
| "Port busy" | Use `exclusive=True` or check `lsof` | [Serial Guide](./SERIAL_INTEGRATION_GUIDE.md#common-issues--solutions) |
| "Permission denied" | Add user to `dialout` group | [Configuration](./CONFIGURATION.md#permissions) |
| High memory usage | Reduce buffer size | [Buffer Architecture](./CIRCULAR_BUFFER_ARCHITECTURE.md#configuration) |
| Missing data | Check drop rate, increase buffer | [Buffer Architecture](./CIRCULAR_BUFFER_ARCHITECTURE.md#troubleshooting) |
| ESP32 not detected | Install ESP32 core | [ESP32 Guide](./ESP32_GUIDE.md) |

## 📝 Documentation Standards

All documentation follows these principles:

- **Clear Structure**: Organized by user journey and use case
- **Practical Examples**: Real code that works
- **Progressive Disclosure**: Start simple, add complexity
- **Cross-References**: Links between related topics
- **Visual Aids**: Diagrams, tables, and formatted output

## 🤝 Contributing

To contribute documentation:

1. Follow existing formatting patterns
2. Include working examples
3. Test all code snippets
4. Update this index when adding new docs
5. Ensure cross-references are valid

## 📈 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.2.0 | 2024-01 | Added circular buffer with cursor management |
| 1.1.0 | 2024-01 | Enhanced serial parameters support |
| 1.0.0 | 2024-01 | Initial release with basic serial monitoring |

## 🔗 External Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io)
- [Arduino CLI Documentation](https://arduino.github.io/arduino-cli/)
- [PySerial Documentation](https://pyserial.readthedocs.io)
- [ESP32 Arduino Core](https://github.com/espressif/arduino-esp32)

---

*For questions or issues, please visit the [GitHub repository](https://github.com/evolutis/mcp-arduino-server)*