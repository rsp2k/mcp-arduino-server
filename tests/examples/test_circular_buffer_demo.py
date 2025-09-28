#!/usr/bin/env python3
"""
Demonstration of circular buffer behavior with serial monitor
Shows wraparound, cursor invalidation, and recovery
"""

import asyncio
import os
import sys

# Set small buffer size for demonstration
os.environ['ARDUINO_SERIAL_BUFFER_SIZE'] = '20'  # Very small for demo

# Add project to path
sys.path.insert(0, '/home/rpm/claude/mcp-arduino-server/src')

from mcp_arduino_server.components.circular_buffer import CircularSerialBuffer, SerialDataType


async def demo():
    """Demonstrate circular buffer behavior"""

    # Create buffer with size 20
    buffer = CircularSerialBuffer(max_size=20)
    print("🔄 Circular Buffer Demo (size=20)\n")

    # Add 10 entries
    print("➤ Adding 10 entries...")
    for i in range(10):
        buffer.add_entry(
            port="/dev/ttyUSB0",
            data=f"Message {i}",
            data_type=SerialDataType.RECEIVED
        )

    stats = buffer.get_statistics()
    print(f"  Buffer: {stats['buffer_size']}/{stats['max_size']} entries")
    print(f"  Total added: {stats['total_entries']}")
    print(f"  Dropped: {stats['entries_dropped']}")

    # Create cursor at oldest data
    cursor1 = buffer.create_cursor(start_from="oldest")
    print("\n✓ Created cursor1 at oldest data")

    # Read first 5 entries
    result = buffer.read_from_cursor(cursor1, limit=5)
    print(f"  Read {result['count']} entries:")
    for entry in result['entries']:
        print(f"    [{entry['index']}] {entry['data']}")

    # Add 15 more entries (will cause wraparound)
    print("\n➤ Adding 15 more entries (buffer will wrap)...")
    for i in range(10, 25):
        buffer.add_entry(
            port="/dev/ttyUSB0",
            data=f"Message {i}",
            data_type=SerialDataType.RECEIVED
        )

    stats = buffer.get_statistics()
    print(f"  Buffer: {stats['buffer_size']}/{stats['max_size']} entries")
    print(f"  Total added: {stats['total_entries']}")
    print(f"  Dropped: {stats['entries_dropped']} ⚠️")
    print(f"  Oldest index: {stats['oldest_index']}")
    print(f"  Newest index: {stats['newest_index']}")

    # Check cursor status
    cursor_info = buffer.get_cursor_info(cursor1)
    print("\n🔍 Cursor1 status after wraparound:")
    print(f"  Valid: {cursor_info['is_valid']}")
    print(f"  Position: {cursor_info['position']}")

    # Try to read from invalid cursor
    print("\n➤ Reading from cursor1 (should auto-recover)...")
    result = buffer.read_from_cursor(cursor1, limit=5, auto_recover=True)
    if result['success']:
        print(f"  ✓ Auto-recovered! Read {result['count']} entries:")
        for entry in result['entries']:
            print(f"    [{entry['index']}] {entry['data']}")
        if 'warning' in result:
            print(f"  ⚠️ {result['warning']}")

    # Create new cursor and demonstrate concurrent reading
    cursor2 = buffer.create_cursor(start_from="newest")
    print("\n✓ Created cursor2 at newest data")

    print("\n📊 Final Statistics:")
    stats = buffer.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Cleanup
    buffer.cleanup_invalid_cursors()
    print("\n🧹 Cleaned up invalid cursors")

if __name__ == "__main__":
    asyncio.run(demo())
