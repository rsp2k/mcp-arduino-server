# 🚀 MCP Arduino Server
### **Talk to Your Arduino. Build Projects Faster. Debug with AI.**

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/mcp-arduino.svg)](https://pypi.org/project/mcp-arduino/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tools: 60+](https://img.shields.io/badge/tools-60+-brightgreen.svg)](https://git.supported.systems/MCP/mcp-arduino)

**The Arduino development server that speaks your language.**

</div>

---

## 🎯 What This Does

This MCP server lets you develop Arduino projects through natural conversation with Claude. Instead of clicking through menus and searching for commands, just describe what you want to build.

## 🚀 Quick Start

```bash
# Install and run
uvx mcp-arduino

# Add to Claude Desktop
claude mcp add arduino "uvx mcp-arduino"
```

That's it. Now you can talk to your Arduino.

## 💬 How You'll Actually Use This

### Starting a New Project

```
You: "I want to blink an LED but with a breathing effect instead of harsh on/off"

Claude: I'll create a breathing LED effect using PWM. Let me set that up for you.

        → arduino_create_sketch with sketch_name="BreathingLED"
        → arduino_write_sketch with PWM fade code
        → arduino_compile_sketch
        → arduino_list_boards
        ✓ Found Arduino Uno on /dev/ttyUSB0
        → arduino_upload_sketch

        Done! Your LED will now fade in and out smoothly.
        The effect uses PWM on pin 9 with a sine wave pattern.

You: "Can you make it respond to ambient light?"

Claude: I'll add a light sensor to make it adaptive.
        → arduino_write_sketch with photoresistor code added
        → arduino_compile_sketch
        → arduino_upload_sketch

        ✓ Now it breathes faster in darkness, slower in bright light
        ✓ Connect photoresistor to A0 with a 10k pulldown
```

### Prototyping an IoT Sensor

```
You: "I have a BME280 sensor and want to log temperature to an SD card every 5 minutes"

Claude: I'll set up data logging with timestamps. Let me configure that.

        Checking what you'll need...
        → arduino_lib_deps with library_name="Adafruit_BME280"
        ✓ Needs: Adafruit_Sensor, Adafruit_BusIO, SPI, Wire

        Installing everything...
        → arduino_lib_install_missing
        → arduino_install_library with library_name="SD"

        Creating the data logger...
        → arduino_sketch_new with template="sensor"
        → arduino_write_sketch with BME280 + SD card logging code

        → arduino_compile_sketch
        ✓ Compiled successfully
        → arduino_upload_sketch

        Your data logger is running! File: TEMP_LOG.CSV
        Format: timestamp, temp_C, humidity_%, pressure_hPa

You: "Show me what it's logging"

Claude: → serial_connect with port="/dev/ttyUSB0"
        → serial_read

        [12:34:56] Writing: 2024-01-15 12:34:56, 22.3, 45, 1013
        [12:35:01] SD Card: 847 records saved
        [12:35:01] Free space: 14.2 GB
```

### Debugging Weird Behavior

```
You: "My servo keeps jittering and I don't know why"

Claude: Let's debug this systematically. I'll help you find the issue.

        First, let's monitor what's happening...
        → serial_connect
        → serial_read

        I see the servo position jumping between 89° and 91°.
        Let's check your power supply...

        → arduino_debug_start with your sketch
        → arduino_debug_break at servo.write()
        → arduino_debug_watch with expression="analogRead(A0)"

        Found it! Your potentiometer reading is noisy.
        The analog value fluctuates ±3 even when not moving.

        Here's the fix - adding hysteresis:
        → arduino_write_sketch with deadband code
        → arduino_upload_sketch

        ✓ Servo now stays steady until you move the pot ±5 units
        ✓ No more jittering!
```

### Building Something Fun

```
You: "I want to make a plant moisture monitor that texts me"

Claude: Cool project! I'll set up a WiFi-enabled moisture monitor.

        → arduino_sketch_new with sketch_name="PlantBuddy", template="wifi"

        Installing what we need...
        → arduino_install_library "WiFiManager"  // Easy WiFi setup
        → arduino_install_library "ThingSpeak"   // Free IoT platform

        → arduino_write_sketch with moisture sensor + WiFi code

        Here's what I built:
        - Reads moisture every 30 minutes
        - Connects to your WiFi (captive portal for setup)
        - Sends data to ThingSpeak
        - ThingSpeak can trigger IFTTT → SMS when dry

        → arduino_upload_sketch
        → serial_monitor

        ✓ WiFi AP: "PlantBuddy-Setup"
        ✓ Connect and enter your WiFi credentials
        ✓ Then view data at: thingspeak.com/channels/YOUR_CHANNEL

You: "Can we add a little OLED display?"

Claude: → arduino_install_library "U8g2"  // Universal display library
        → arduino_write_sketch with display code added

        ✓ Display shows: moisture %, WiFi status, last watering
        ✓ Cute plant emoji changes based on moisture level 🌱💧
```

### Working with Existing Code

```
You: "I found this Arduino code online but it won't compile"
[pastes code with errors]

Claude: I see the issues. Let me fix them.

        → arduino_create_sketch "FixedCode"
        → arduino_write_sketch with your code
        → arduino_compile_sketch

        Error: 'dht' was not declared

        Missing library. Installing...
        → arduino_install_library "DHT sensor library"

        → arduino_compile_sketch
        Error: 'POSITIVE' was not declared

        That's from the old LiquidCrystal library.
        → arduino_write_sketch with LCD library fix

        → arduino_compile_sketch
        ✓ Success! The code had 3 issues:
        1. Missing DHT library
        2. Old LCD library syntax
        3. Incorrect pin mode for analog input

        All fixed and ready to upload!
```

### Exploring and Learning

```
You: "What can I build with just LEDs and resistors?"

Claude: Let me show you some fun LED projects you can build right now!

        1. **Knight Rider Scanner**
        → arduino_create_sketch "KnightRider"
        → arduino_write_sketch with 6-LED scanner effect
        ✓ Creates that classic back-and-forth sweep

        2. **Binary Counter**
        → arduino_create_sketch "BinaryCounter"
        → arduino_write_sketch with 4-bit binary display
        ✓ Counts 0-15 in binary on 4 LEDs

        3. **Morse Code Sender**
        → arduino_create_sketch "MorseCode"
        → arduino_write_sketch with text-to-morse converter
        ✓ Type messages in serial monitor, see them in Morse!

        4. **LED Dice**
        → arduino_create_sketch "LEDDice"
        → arduino_write_sketch with 7-LED dice pattern
        ✓ Press button to "roll" - shows dice dots

        Want to try any of these? I can upload one now!
```

## 🛠️ Key Features for Your Workflow

### 🔄 **Never Lose Serial Data**
Our circular buffer means you can leave projects running for days without memory crashes:
```
You: "Show me the overnight temperature log"
Claude: → serial_read with cursor navigation
        ✓ Showing last 1000 of 28,847 readings
        ✓ Memory usage: still just 10MB (fixed size)
```

### 🔍 **Auto-Detect Everything**
No more guessing board types or ports:
```
You: "What's connected?"
Claude: → arduino_list_boards
        ✓ Found: Arduino Uno on /dev/ttyUSB0
        ✓ Found: ESP32-DevKit on /dev/ttyUSB1
```

### 📚 **Smart Library Management**
Never hunt for dependencies again:
```
You: "Add a GPS module"
Claude: → arduino_lib_deps "TinyGPSPlus"
        → arduino_lib_install_missing
        ✓ Installed TinyGPSPlus and all dependencies
```

### ⚡ **Fast Compilation**
Parallel builds with caching make iteration quick:
```
You: "Compile this"
Claude: → arduino_compile_advanced with jobs=4
        ✓ Compiled in 8 seconds (using 4 CPU cores)
```

### 🐛 **Real Debugging**
Not just Serial.println() - actual breakpoints and variable inspection:
```
You: "Why does it crash in the interrupt handler?"
Claude: → arduino_debug_start
        → arduino_debug_break at ISR function
        → arduino_debug_watch with timer variables
        ✓ Found it: Integer overflow at timer > 65535
```

## 📦 What You Get

**60+ Tools** organized into logical groups:
- **Sketch Operations**: Create, read, write, compile, upload
- **Library Management**: Search, install, dependency resolution
- **Board Management**: Detection, configuration, core installation
- **Serial Monitoring**: Memory-safe buffering, cursor pagination
- **Debugging**: GDB integration, breakpoints, memory inspection
- **Project Templates**: WiFi, sensor, serial, blink patterns
- **Circuit Diagrams**: Generate wiring diagrams from descriptions

## 🎓 Perfect For

- **Beginners**: "How do I connect a button?" → Get working code instantly
- **Makers**: "Add WiFi to my weather station" → Dependencies handled automatically
- **Students**: "Debug my robot code" → Find issues with AI assistance
- **Engineers**: "Profile memory usage" → Professional debugging tools included

## 🔧 Configuration

Set your preferences via environment variables:
```bash
ARDUINO_CLI_PATH=arduino-cli
ARDUINO_SERIAL_BUFFER_SIZE=10000     # Circular buffer size
MCP_SKETCH_DIR=~/Arduino_Projects    # Where sketches are saved
```

## 🚦 Requirements

- **Python 3.10+**
- **arduino-cli** ([install guide](https://arduino.github.io/arduino-cli/installation/))
- **Claude Desktop** or any MCP-compatible client

## 📚 Examples Repository

Check out [examples/](./examples/) for complete projects:
- IoT weather station
- LED matrix games
- Sensor data logger
- Bluetooth robot controller
- Home automation basics

## 🤝 Contributing

We love contributions! Whether it's adding new templates, fixing bugs, or improving documentation.

```bash
git clone https://git.supported.systems/MCP/mcp-arduino
cd mcp-arduino
uv pip install -e ".[dev]"
pytest tests/
```

## 📜 License

MIT - Use it, modify it, share it!

## 🙏 Built With

- [Arduino CLI](https://github.com/arduino/arduino-cli) - The foundation
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP framework
- [pySerial](https://github.com/pyserial/pyserial) - Serial communication

---

<div align="center">

### **Ready to start building?**

```bash
uvx mcp-arduino
```

**Talk to your Arduino. Build something awesome.**

[Documentation](./docs/README.md) • [Report Issues](https://git.supported.systems/MCP/mcp-arduino/issues) • [Discord Community](#)

</div>