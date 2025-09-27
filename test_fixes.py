#!/usr/bin/env python3
"""Test the fixed Arduino compile advanced functionality"""

import asyncio
import sys
from pathlib import Path

# Add the source directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_arduino_server.config import ArduinoServerConfig
from mcp_arduino_server.components.arduino_compile_advanced import ArduinoCompileAdvanced

async def test_compile_and_size():
    """Test the compilation and size analysis tools"""

    # Initialize configuration
    config = ArduinoServerConfig()

    # Create compile component
    compiler = ArduinoCompileAdvanced(config)

    print("Testing arduino_compile_advanced...")

    # Test compilation
    compile_result = await compiler.compile_advanced(
        sketch_name="TestCompile",
        fqbn="esp32:esp32:esp32",
        warnings="all",
        export_binaries=True,
        build_properties=None,
        build_cache_path=None,
        libraries=None,
        optimize_for_debug=False,
        preprocess_only=False,
        show_properties=False,
        verbose=False,
        vid_pid=None,
        jobs=None,
        clean=False,
        ctx=None
    )

    print(f"Compile result: {compile_result}")
    print(f"Build path: {compile_result.get('build_path')}")

    print("\nTesting arduino_size_analysis...")

    # Test size analysis
    size_result = await compiler.analyze_size(
        sketch_name="TestCompile",
        fqbn="esp32:esp32:esp32",
        build_path=None,
        detailed=True,
        ctx=None
    )

    print(f"Size analysis result: {size_result}")

    if size_result.get("success"):
        print(f"Flash used: {size_result.get('flash_used')} bytes")
        print(f"RAM used: {size_result.get('ram_used')} bytes")

if __name__ == "__main__":
    asyncio.run(test_compile_and_size())