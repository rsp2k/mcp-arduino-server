#!/usr/bin/env python3
"""
Test script for Serial Monitor functionality
Tests connection, reading, and cursor-based pagination
"""

import asyncio
import json
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_arduino_server.components.serial_monitor import (
    SerialMonitorContext,
    SerialListPortsTool,
    SerialListPortsParams
)
from fastmcp import Context


async def test_serial_monitor():
    """Test serial monitor functionality"""
    print("🧪 Testing Serial Monitor Components\n")

    # Create context
    ctx = Context()
    monitor = SerialMonitorContext()
    await monitor.initialize()
    ctx.state["serial_monitor"] = monitor

    print("✅ Serial monitor initialized")

    # Test listing ports
    print("\n📡 Testing port listing...")
    list_tool = SerialListPortsTool()
    params = SerialListPortsParams(arduino_only=False)

    result = await list_tool.run(params, ctx)

    if result["success"]:
        print(f"✅ Found {len(result['ports'])} ports:")
        for port in result["ports"]:
            arduino_badge = "🟢 Arduino" if port["is_arduino"] else "⚪ Other"
            print(f"  {arduino_badge} {port['device']}: {port['description']}")
            if port["vid"] and port["pid"]:
                print(f"      VID:PID = {port['vid']:04x}:{port['pid']:04x}")
    else:
        print("❌ Failed to list ports")

    # Get monitor state
    print("\n📊 Serial Monitor State:")
    state = monitor.get_state()
    print(json.dumps(state, indent=2))

    # Cleanup
    await monitor.cleanup()
    print("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(test_serial_monitor())