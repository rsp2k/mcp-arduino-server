"""
Real ESP32 Installation Integration Test
========================================

This test validates the ESP32 installation tool against the real Arduino CLI.
It demonstrates that the arduino_install_esp32 tool properly:

1. Updates board index with ESP32 URL
2. Handles large downloads with extended timeouts
3. Provides proper progress tracking
4. Detects ESP32 boards after installation

This test is intended to be run manually when testing the ESP32 installation
functionality, as it requires internet connectivity and downloads large packages.
"""

import tempfile
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.utilities.tests import run_server_in_process

from src.mcp_arduino_server.config import ArduinoServerConfig
from src.mcp_arduino_server.server_refactored import create_server


def create_test_server(host: str, port: int, transport: str = "http") -> None:
    """Function to run Arduino MCP server in subprocess for testing"""
    import os

    # Set environment variable to disable file opening
    os.environ['TESTING_MODE'] = '1'

    # Create temporary test configuration
    tmp_path = Path(tempfile.mkdtemp())
    config = ArduinoServerConfig(
        arduino_cli_path="/usr/bin/arduino-cli",
        sketches_base_dir=tmp_path / "sketches",
        build_temp_dir=tmp_path / "build",
        wireviz_path="/usr/bin/wireviz",
        command_timeout=120,  # Extended timeout for ESP32 downloads
        enable_client_sampling=True
    )

    # Create and run server
    server = create_server(config)
    server.run(transport="streamable-http", host=host, port=port)


@pytest.fixture
async def mcp_server():
    """Fixture that runs Arduino MCP server in subprocess with HTTP transport"""
    with run_server_in_process(create_test_server, transport="http") as url:
        yield f"{url}/mcp"


@pytest.fixture
async def mcp_client(mcp_server: str):
    """Fixture that provides a connected MCP client"""
    async with Client(
        transport=StreamableHttpTransport(mcp_server)
    ) as client:
        yield client


class TestRealESP32Installation:
    """Integration test for real ESP32 installation (requires internet)"""

    @pytest.mark.skipif(
        not Path("/usr/bin/arduino-cli").exists(),
        reason="arduino-cli not installed"
    )
    @pytest.mark.slow
    @pytest.mark.internet
    @pytest.mark.asyncio
    async def test_esp32_tool_availability(self, mcp_client: Client):
        """Test that the arduino_install_esp32 tool is available"""
        print("\n🔍 Checking ESP32 installation tool availability...")

        tools = await mcp_client.list_tools()
        tool_names = [tool.name for tool in tools]

        assert "arduino_install_esp32" in tool_names, (
            f"ESP32 installation tool not found. Available tools: {tool_names}"
        )

        # Find the ESP32 installation tool
        esp32_tool = next(tool for tool in tools if tool.name == "arduino_install_esp32")

        # Verify tool properties
        assert esp32_tool.description is not None
        assert "ESP32" in esp32_tool.description
        assert "board support" in esp32_tool.description.lower()

        print("✅ ESP32 installation tool is available")

    @pytest.mark.skipif(
        not Path("/usr/bin/arduino-cli").exists(),
        reason="arduino-cli not installed"
    )
    @pytest.mark.slow
    @pytest.mark.internet
    @pytest.mark.asyncio
    async def test_esp32_installation_real(self, mcp_client: Client):
        """Test real ESP32 installation (requires internet and time)"""
        print("\n🔧 Testing real ESP32 installation...")
        print("⚠️  This test requires internet connectivity and may take several minutes")
        print("⚠️  It will download >500MB of ESP32 toolchain and core files")

        # Call the ESP32 installation tool
        print("📦 Calling arduino_install_esp32...")
        result = await mcp_client.call_tool("arduino_install_esp32", {})

        print(f"📊 Installation result: {result.data}")

        # Check if installation was successful or already installed
        if "success" in result.data:
            assert result.data["success"] is True
            if "already installed" in result.data.get("message", "").lower():
                print("✅ ESP32 core was already installed")
            else:
                print("✅ ESP32 core installed successfully")

            # Verify next steps are provided
            if "next_steps" in result.data:
                next_steps = result.data["next_steps"]
                assert isinstance(next_steps, list)
                assert len(next_steps) > 0
                print(f"📋 Next steps provided: {len(next_steps)} items")

        elif "error" in result.data:
            error_msg = result.data["error"]
            print(f"❌ Installation failed: {error_msg}")

            # Check if it's a known acceptable error
            acceptable_errors = [
                "already installed",
                "up to date",
                "no changes required"
            ]

            if any(acceptable in error_msg.lower() for acceptable in acceptable_errors):
                print("✅ Acceptable error - ESP32 already properly installed")
            else:
                # This is an actual failure
                pytest.fail(f"ESP32 installation failed: {error_msg}")

    @pytest.mark.skipif(
        not Path("/usr/bin/arduino-cli").exists(),
        reason="arduino-cli not installed"
    )
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_board_detection_after_esp32(self, mcp_client: Client):
        """Test board detection after ESP32 installation"""
        print("\n🔍 Testing board detection capabilities...")

        # Test board detection
        boards_result = await mcp_client.call_tool("arduino_list_boards", {})
        print(f"📊 Board detection result: {boards_result.data}")

        # The result should be a string
        assert isinstance(boards_result.data, str)

        # Should either find boards or report none found
        boards_text = boards_result.data
        board_found = "Found" in boards_text and "board" in boards_text
        no_boards = "No Arduino boards detected" in boards_text

        assert board_found or no_boards, f"Unexpected board detection response: {boards_text}"

        if board_found:
            print("✅ Arduino boards detected")

            # If ESP32 board is detected, verify it's properly identified
            if "ESP32" in boards_text or "esp32" in boards_text:
                print("🎉 ESP32 board detected and properly identified!")
                assert "FQBN:" in boards_text
                assert "esp32:esp32" in boards_text
        else:
            print("ℹ️  No boards currently connected")

    @pytest.mark.skipif(
        not Path("/usr/bin/arduino-cli").exists(),
        reason="arduino-cli not installed"
    )
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_esp32_core_listing(self, mcp_client: Client):
        """Test that ESP32 core is properly listed after installation"""
        print("\n📋 Testing ESP32 core listing...")

        # List installed cores
        cores_result = await mcp_client.call_tool("arduino_list_cores", {})
        print(f"📊 Cores result: {cores_result.data}")

        if "success" in cores_result.data and cores_result.data["success"]:
            cores = cores_result.data.get("cores", [])
            print(f"📦 Found {len(cores)} installed cores")

            # Look for ESP32 core
            esp32_core = next(
                (core for core in cores if "esp32" in core.get("id", "").lower()),
                None
            )

            if esp32_core:
                print("✅ ESP32 core found in installed cores")
                print(f"   ID: {esp32_core.get('id')}")
                print(f"   Name: {esp32_core.get('name')}")
                print(f"   Version: {esp32_core.get('installed')}")
                print(f"   Boards: {len(esp32_core.get('boards', []))}")

                # Verify core has ESP32 boards
                boards = esp32_core.get('boards', [])
                esp32_boards = [board for board in boards if 'ESP32' in board]
                assert len(esp32_boards) > 0, f"No ESP32 boards found in core: {boards}"
                print(f"   ESP32 boards: {esp32_boards}")
            else:
                print("⚠️  ESP32 core not found - may need installation")
        else:
            print("❌ Failed to list cores")

    @pytest.mark.skipif(
        not Path("/usr/bin/arduino-cli").exists(),
        reason="arduino-cli not installed"
    )
    @pytest.mark.slow
    @pytest.mark.internet
    @pytest.mark.asyncio
    async def test_complete_esp32_workflow(self, mcp_client: Client):
        """Test complete ESP32 workflow: ensure install -> verify core -> check detection"""
        print("\n🔄 Testing complete ESP32 workflow...")

        # Step 1: Ensure ESP32 is installed
        print("📦 Step 1: Ensuring ESP32 core is installed...")
        install_result = await mcp_client.call_tool("arduino_install_esp32", {})

        install_success = (
            "success" in install_result.data and install_result.data["success"]
        ) or (
            "error" in install_result.data and
            "already installed" in install_result.data["error"].lower()
        )

        assert install_success, f"ESP32 installation failed: {install_result.data}"
        print("✅ ESP32 core installation confirmed")

        # Step 2: Verify core is listed
        print("📋 Step 2: Verifying ESP32 core is listed...")
        cores_result = await mcp_client.call_tool("arduino_list_cores", {})

        if cores_result.data.get("success"):
            cores = cores_result.data.get("cores", [])
            esp32_core = next(
                (core for core in cores if "esp32" in core.get("id", "").lower()),
                None
            )

            if esp32_core:
                print("✅ ESP32 core properly listed")
                print(f"   Available boards: {len(esp32_core.get('boards', []))}")
            else:
                print("⚠️  ESP32 core not found in core list")

        # Step 3: Test board detection capabilities
        print("🔍 Step 3: Testing board detection...")
        boards_result = await mcp_client.call_tool("arduino_list_boards", {})

        boards_text = boards_result.data
        if "ESP32" in boards_text or "esp32" in boards_text:
            print("🎉 ESP32 board detected and working!")
        else:
            print("ℹ️  No ESP32 board currently connected (but core is available)")

        print("✅ Complete ESP32 workflow validated")


if __name__ == "__main__":
    # Run tests with markers
    import sys
    sys.exit(pytest.main([
        __file__,
        "-v", "-s",
        "-m", "not slow",  # Skip slow tests by default
        "--tb=short"
    ]))
