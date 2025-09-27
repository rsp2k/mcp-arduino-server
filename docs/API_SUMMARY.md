# 📘 API Reference Summary

> Quick reference for all MCP Arduino Server tools and resources

## 🛠️ Tools by Category

### 📝 Sketch Management

```python
# Create new sketch
await arduino_create_sketch(sketch_name="MyProject")

# Write/update sketch (auto-compiles)
await arduino_write_sketch(
    sketch_name="MyProject",
    content="void setup() {...}",
    auto_compile=True  # Default
)

# Read sketch
await arduino_read_sketch(
    sketch_name="MyProject",
    file_name=None  # Main .ino file
)

# List all sketches
await arduino_list_sketches()

# Compile without upload
await arduino_compile_sketch(
    sketch_name="MyProject",
    board_fqbn=""  # Auto-detect
)

# Upload to board
await arduino_upload_sketch(
    sketch_name="MyProject",
    port="/dev/ttyUSB0",
    board_fqbn=""  # Auto-detect
)
```

### 📡 Serial Communication

```python
# Connect with full parameters
await serial_connect(
    port="/dev/ttyUSB0",
    baudrate=115200,        # 9600, 19200, 38400, 57600, 115200, etc.
    bytesize=8,            # 5, 6, 7, or 8
    parity='N',            # 'N'=None, 'E'=Even, 'O'=Odd, 'M'=Mark, 'S'=Space
    stopbits=1,            # 1, 1.5, or 2
    xonxoff=False,         # Software flow control
    rtscts=False,          # Hardware (RTS/CTS) flow control
    dsrdtr=False,          # Hardware (DSR/DTR) flow control
    auto_monitor=True,     # Start monitoring automatically
    exclusive=False        # Disconnect other ports first
)

# Send data
await serial_send(
    port="/dev/ttyUSB0",
    data="Hello Arduino",
    add_newline=True,      # Add \n automatically
    wait_response=False,   # Wait for response
    timeout=5.0           # Response timeout
)

# Read with cursor
result = await serial_read(
    cursor_id=None,        # Use existing cursor
    port=None,            # Filter by port
    limit=100,            # Max entries to return
    type_filter=None,     # Filter: received/sent/system/error
    create_cursor=False,  # Create new cursor
    start_from="oldest",  # oldest/newest/next
    auto_recover=True     # Recover invalid cursors
)
```

### 📦 Library Management

```python
# Search libraries
await arduino_search_libraries(
    query="servo",
    limit=10
)

# Install library
await arduino_install_library(
    library_name="Servo",
    version=None  # Latest
)

# List examples
await arduino_list_library_examples(
    library_name="Servo"
)

# Uninstall library
await arduino_uninstall_library(
    library_name="Servo"
)
```

### 🎛️ Board Management

```python
# List connected boards
await arduino_list_boards()

# Search board definitions
await arduino_search_boards(
    query="esp32"
)

# Install board core
await arduino_install_core(
    core_spec="esp32:esp32"
)

# Install ESP32 (convenience)
await arduino_install_esp32()

# List installed cores
await arduino_list_cores()

# Update all cores
await arduino_update_cores()
```

### 🐛 Debug Operations

```python
# Start debug session
session_id = await arduino_debug_start(
    sketch_name="MySketch",
    port="/dev/ttyUSB0",
    board_fqbn="",
    gdb_port=4242
)

# Interactive debugging
await arduino_debug_interactive(
    session_id=session_id,
    auto_mode=False,      # User controls
    auto_strategy="continue",
    auto_watch=True
)

# Set breakpoint
await arduino_debug_break(
    session_id=session_id,
    location="loop:10",   # Function:line
    condition=None,
    temporary=False
)

# Print variable
await arduino_debug_print(
    session_id=session_id,
    expression="myVariable"
)

# Stop session
await arduino_debug_stop(
    session_id=session_id
)
```

### 🔌 Circuit Diagrams

```python
# From natural language (AI)
await wireviz_generate_from_description(
    description="Arduino connected to LED on pin 13",
    output_base="circuit",
    sketch_name=""
)

# From YAML
await wireviz_generate_from_yaml(
    yaml_content="...",
    output_base="circuit"
)
```

### 🔄 Cursor Management

```python
# Get cursor info
await serial_cursor_info(
    cursor_id="uuid-here"
)

# List all cursors
await serial_list_cursors()

# Delete cursor
await serial_delete_cursor(
    cursor_id="uuid-here"
)

# Cleanup invalid
await serial_cleanup_cursors()
```

### 📊 Buffer Management

```python
# Get statistics
stats = await serial_buffer_stats()
# Returns: buffer_size, max_size, usage_percent,
#          total_entries, entries_dropped, drop_rate

# Resize buffer
await serial_resize_buffer(
    new_size=50000  # 100-1000000
)

# Clear buffer
await serial_clear_buffer(
    port=None  # All ports
)

# Monitor state
state = await serial_monitor_state()
```

## 📚 Resources

```python
# Available resources
"arduino://sketches"        # List of all sketches
"arduino://boards"          # Connected boards info
"arduino://libraries"       # Installed libraries
"arduino://cores"          # Installed board cores
"arduino://serial/state"   # Serial monitor state
"wireviz://instructions"   # WireViz usage guide
```

## 🔄 Return Value Patterns

### Success Response
```python
{
    "success": True,
    "data": {...},
    "message": "Operation completed"
}
```

### Error Response
```python
{
    "success": False,
    "error": "Error message",
    "details": {...}
}
```

### Serial Read Response
```python
{
    "success": True,
    "cursor_id": "uuid",
    "entries": [
        {
            "timestamp": "2024-01-01T12:00:00",
            "type": "received",  # received/sent/system/error
            "data": "Hello from Arduino",
            "port": "/dev/ttyUSB0",
            "index": 42
        }
    ],
    "count": 10,
    "has_more": True,
    "cursor_state": {...},
    "buffer_state": {...}
}
```

### Board List Response
```python
{
    "success": True,
    "boards": [
        {
            "port": "/dev/ttyUSB0",
            "fqbn": "arduino:avr:uno",
            "name": "Arduino Uno",
            "vid": "2341",
            "pid": "0043"
        }
    ]
}
```

## ⚡ Common Patterns

### Continuous Monitoring
```python
cursor = await serial_read(create_cursor=True)
while True:
    data = await serial_read(
        cursor_id=cursor['cursor_id'],
        limit=10
    )
    for entry in data['entries']:
        process(entry)
    if not data['has_more']:
        await asyncio.sleep(0.1)
```

### Upload and Monitor
```python
# Upload sketch
await arduino_upload_sketch(sketch_name="Test", port=port)

# Connect to serial
await serial_connect(port=port, baudrate=115200)

# Monitor output
cursor = await serial_read(create_cursor=True)
```

### Multi-Board Management
```python
boards = await arduino_list_boards()
for board in boards['boards']:
    await serial_connect(
        port=board['port'],
        exclusive=False
    )
```

## 🎯 Best Practices

1. **Always use cursors** for continuous reading
2. **Enable auto_recover** for robust operation
3. **Set exclusive=True** to avoid port conflicts
4. **Check buffer statistics** regularly
5. **Use appropriate buffer size** for data rate
6. **Handle errors gracefully** with try/except
7. **Close connections** when done

## 🔗 See Also

- [Full Serial Monitor API](./SERIAL_MONITOR.md)
- [Configuration Guide](./CONFIGURATION.md)
- [Examples](./EXAMPLES.md)
- [Troubleshooting](./SERIAL_INTEGRATION_GUIDE.md#common-issues--solutions)

---

*This is a summary. For complete documentation, see the full API reference.*