# 🔄 Circular Buffer Architecture

## Overview

The MCP Arduino Server uses a sophisticated circular buffer implementation for managing serial data streams. This ensures bounded memory usage while maintaining high performance for long-running serial monitoring sessions.

## Key Features

### 1. **Fixed Memory Footprint**
- Configurable maximum size via `ARDUINO_SERIAL_BUFFER_SIZE` environment variable
- Default: 10,000 entries
- Range: 100 to 1,000,000 entries
- Automatic memory management prevents unbounded growth

### 2. **Cursor-Based Reading**
- Multiple independent cursors for concurrent consumers
- Each cursor maintains its own read position
- No interference between different clients/consumers

### 3. **Automatic Wraparound**
- When buffer reaches capacity, oldest entries are automatically removed
- Seamless operation without manual intervention
- Statistics track dropped entries for monitoring

### 4. **Cursor Invalidation & Recovery**
- Cursors pointing to overwritten data are marked invalid
- Auto-recovery option jumps to oldest available data
- Prevents reading stale or corrupted data

## Architecture

```
┌─────────────────────────────────────────┐
│         Circular Buffer (deque)         │
├─────────────────────────────────────────┤
│  [5] [6] [7] ... [23] [24]             │
│   ↑                      ↑              │
│ oldest                newest            │
└─────────────────────────────────────────┘
         ↑            ↑           ↑
      Cursor1      Cursor2     Cursor3
     (pos: 7)     (pos: 15)   (invalid)
```

## Configuration

### Environment Variables

```bash
# Set buffer size (default: 10000)
export ARDUINO_SERIAL_BUFFER_SIZE=50000  # For high-speed logging

# Or in .env file
ARDUINO_SERIAL_BUFFER_SIZE=50000
```

### Size Recommendations

| Use Case | Recommended Size | Rationale |
|----------|-----------------|-----------|
| Basic debugging | 1,000 - 5,000 | Low memory usage, sufficient for debugging |
| Normal operation | 10,000 (default) | Balance between memory and data retention |
| High-speed logging | 50,000 - 100,000 | Captures more data before wraparound |
| Long-term monitoring | 100,000 - 1,000,000 | Maximum retention, higher memory usage |

## API Features

### Cursor Creation Options

```python
# Start from oldest available data
cursor = buffer.create_cursor(start_from="oldest")

# Start from newest entry
cursor = buffer.create_cursor(start_from="newest")

# Start from next entry to be added
cursor = buffer.create_cursor(start_from="next")

# Start from absolute beginning (may be invalid)
cursor = buffer.create_cursor(start_from="beginning")
```

### Reading with Recovery

```python
# Auto-recover from invalid cursor
result = buffer.read_from_cursor(
    cursor_id=cursor,
    limit=100,
    auto_recover=True  # Jump to oldest if invalid
)

# Check for warnings
if 'warning' in result:
    print(f"Recovery: {result['warning']}")
```

### Buffer Statistics

```python
stats = buffer.get_statistics()
# Returns:
{
    "buffer_size": 1000,        # Current entries
    "max_size": 10000,          # Maximum capacity
    "usage_percent": 10.0,      # Buffer utilization
    "total_entries": 5000,      # Total entries added
    "entries_dropped": 0,       # Entries lost to wraparound
    "drop_rate": 0.0,          # Percentage dropped
    "oldest_index": 4000,       # Oldest entry index
    "newest_index": 4999,       # Newest entry index
    "active_cursors": 3,        # Total cursors
    "valid_cursors": 2,         # Valid cursors
    "invalid_cursors": 1        # Invalid cursors
}
```

### Cursor Management

```python
# List all cursors
cursors = buffer.list_cursors()

# Get cursor information
info = buffer.get_cursor_info(cursor_id)
# Returns: position, validity, read stats

# Cleanup invalid cursors
removed = buffer.cleanup_invalid_cursors()

# Delete specific cursor
buffer.delete_cursor(cursor_id)
```

### Dynamic Buffer Resizing

```python
# Resize buffer (may drop old data if shrinking)
result = buffer.resize_buffer(new_size=5000)
# Returns: old_size, new_size, entries_dropped
```

## Performance Characteristics

### Time Complexity
- **Add entry**: O(1) - Constant time append
- **Read from cursor**: O(n) - Linear scan with early exit
- **Create cursor**: O(1) - Constant time
- **Delete cursor**: O(1) - Hash map removal

### Space Complexity
- **Fixed memory**: O(max_size) - Bounded by configuration
- **Per cursor overhead**: O(1) - Minimal metadata

## Use Cases

### 1. High-Speed Data Logging
```python
# Configure for 100Hz sensor data
os.environ['ARDUINO_SERIAL_BUFFER_SIZE'] = '100000'
# 100,000 entries = ~16 minutes at 100Hz
```

### 2. Multiple Client Monitoring
```python
# Each client gets independent cursor
client1_cursor = buffer.create_cursor()
client2_cursor = buffer.create_cursor()
# Clients read at their own pace
```

### 3. Memory-Constrained Systems
```python
# Raspberry Pi or embedded system
os.environ['ARDUINO_SERIAL_BUFFER_SIZE'] = '1000'
# Small buffer, frequent reads required
```

## Monitoring & Debugging

### Check Buffer Health
```python
async def monitor_buffer_health():
    while True:
        stats = await serial_buffer_stats()

        # Alert on high drop rate
        if stats['drop_rate'] > 10:
            print(f"⚠️ High drop rate: {stats['drop_rate']}%")
            print("Consider increasing buffer size")

        # Alert on invalid cursors
        if stats['invalid_cursors'] > 0:
            print(f"⚠️ {stats['invalid_cursors']} invalid cursors")
            await serial_cleanup_cursors()

        await asyncio.sleep(60)  # Check every minute
```

### Debug Cursor Issues
```python
# Check why cursor is invalid
cursor_info = await serial_cursor_info(cursor_id)
if not cursor_info['is_valid']:
    print(f"Cursor invalid - position {cursor_info['position']}")
    print(f"Buffer oldest: {stats['oldest_index']}")
    # Position is before oldest = overwritten
```

## Best Practices

1. **Size appropriately**: Match buffer size to data rate and read frequency
2. **Monitor statistics**: Track drop rate to detect sizing issues
3. **Use auto-recovery**: Enable for robust operation
4. **Cleanup regularly**: Remove invalid cursors periodically
5. **Read frequently**: Prevent buffer overflow with regular reads

## Implementation Details

The circular buffer uses Python's `collections.deque` with `maxlen` parameter:

```python
from collections import deque

class CircularSerialBuffer:
    def __init__(self, max_size: int = 10000):
        self.buffer = deque(maxlen=max_size)  # Auto-wraparound
        self.global_index = 0  # Ever-incrementing
        self.cursors = {}  # Cursor tracking
```

This provides:
- Automatic oldest entry removal when full
- O(1) append and popleft operations
- Efficient memory usage
- Thread-safe operations (with GIL)

## Comparison with Alternatives

| Approach | Pros | Cons |
|----------|------|------|
| **Circular Buffer** (current) | Bounded memory, auto-cleanup, efficient | May lose old data |
| **Unlimited List** | Never loses data | Unbounded memory growth |
| **Database** | Persistent, queryable | Slower, disk I/O |
| **Ring Buffer (fixed array)** | Very efficient | Less flexible than deque |

## Future Enhancements

Potential improvements for future versions:

1. **Persistence**: Optional disk backing for important data
2. **Compression**: Compress old entries to increase capacity
3. **Filtering**: Built-in filtering at buffer level
4. **Metrics**: Prometheus/Grafana integration
5. **Sharding**: Multiple buffers for different data streams

## Troubleshooting

### Problem: High drop rate
**Solution**: Increase `ARDUINO_SERIAL_BUFFER_SIZE` or read more frequently

### Problem: Invalid cursors
**Solution**: Enable `auto_recover=True` or create new cursors

### Problem: Memory usage too high
**Solution**: Decrease buffer size or implement pagination

### Problem: Missing data
**Solution**: Check `entries_dropped` statistic, consider larger buffer

## Conclusion

The circular buffer provides a robust, memory-efficient solution for serial data management. With configurable sizing, automatic wraparound, and cursor-based reading, it handles both high-speed logging and long-running monitoring sessions effectively.