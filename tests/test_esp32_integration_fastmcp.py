"""
ESP32 Installation Integration Test using FastMCP Server
========================================================

This test file validates the ESP32 installation tool using the FastMCP run_server_in_process pattern.
It tests the complete workflow:

1. Start MCP server with FastMCP integration testing pattern
2. Call arduino_install_esp32 tool to install ESP32 support
3. Verify installation was successful with proper progress tracking
4. Test arduino_list_boards to confirm ESP32 board detection on /dev/ttyUSB0
5. Verify ESP32 core is properly listed in arduino_list_cores

This addresses the ESP32 core installation timeout issues by using the specialized
arduino_install_esp32 tool that handles large downloads (>500MB) with extended timeouts.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

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
        command_timeout=30,
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


class TestESP32InstallationIntegration:
    """Integration test suite for ESP32 installation using FastMCP server"""

    @pytest.mark.asyncio
    async def test_esp32_installation_tool_availability(self, mcp_client: Client):
        """Verify that the arduino_install_esp32 tool is properly registered"""
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

    @pytest.mark.asyncio
    async def test_esp32_installation_successful_flow(self, mcp_client: Client):
        """Test successful ESP32 installation with complete mocking"""

        print("\n🔧 Testing ESP32 installation successful flow...")

        # Mock subprocess operations at the component level
        with patch('src.mcp_arduino_server.components.arduino_board.asyncio.create_subprocess_exec') as mock_create_subprocess:

            # Mock index update process (successful)
            mock_index_process = AsyncMock()
            mock_index_process.returncode = 0
            mock_index_process.communicate.return_value = (
                b"Updating index: package_index.json downloaded",
                b""
            )

            # Mock ESP32 core installation process (successful)
            mock_install_process = AsyncMock()
            mock_install_process.returncode = 0
            mock_install_process.wait = AsyncMock()

            # Create mock streams for progress tracking
            stdout_messages = [
                b"Downloading esp32:esp32@2.0.11...\n",
                b"esp32:esp32@2.0.11 downloaded\n",
                b"Downloading xtensa-esp32-elf-gcc@8.4.0+2021r2-patch5...\n",
                b"xtensa-esp32-elf-gcc@8.4.0+2021r2-patch5 downloaded\n",
                b"Installing esp32:esp32@2.0.11...\n",
                b"Installing xtensa-esp32-elf-gcc@8.4.0+2021r2-patch5...\n",
                b"Platform esp32:esp32@2.0.11 installed\n",
                b""  # End of stream
            ]

            message_index = 0
            async def mock_stdout_readline():
                nonlocal message_index
                if message_index < len(stdout_messages):
                    msg = stdout_messages[message_index]
                    message_index += 1
                    return msg
                return b""

            mock_stdout = AsyncMock()
            mock_stderr = AsyncMock()
            mock_stdout.readline = mock_stdout_readline
            mock_stderr.readline = AsyncMock(return_value=b"")

            mock_install_process.stdout = mock_stdout
            mock_install_process.stderr = mock_stderr

            # Configure mock to return appropriate process for each command
            def mock_subprocess_factory(*args, **kwargs):
                cmd = args if args else kwargs.get('args', [])
                if any('update-index' in str(arg) for arg in cmd):
                    return mock_index_process
                else:  # Core installation
                    return mock_install_process

            mock_create_subprocess.side_effect = mock_subprocess_factory

            # Mock the final board list command
            with patch('src.mcp_arduino_server.components.arduino_board.subprocess.run') as mock_subprocess_run:
                mock_subprocess_run.return_value.returncode = 0
                mock_subprocess_run.return_value.stdout = (
                    "FQBN                   Board Name\n"
                    "esp32:esp32:esp32      ESP32 Dev Module\n"
                    "esp32:esp32:esp32wrover ESP32 Wrover Module\n"
                )

                print("📦 Calling arduino_install_esp32 tool...")

                # Execute the ESP32 installation
                result = await mcp_client.call_tool("arduino_install_esp32", {})

                print(f"📊 Installation result: {result.data}")

                # Verify successful installation
                assert "success" in result.data, f"Expected success in result: {result.data}"
                assert result.data["success"] is True, f"Installation failed: {result.data}"
                assert "ESP32 core installed successfully" in result.data["message"]

                # Verify next steps are provided
                assert "next_steps" in result.data
                next_steps = result.data["next_steps"]
                assert isinstance(next_steps, list)
                assert len(next_steps) > 0

                # Verify next steps contain useful information
                next_steps_text = " ".join(next_steps)
                assert "Connect your ESP32 board" in next_steps_text
                assert "arduino_list_boards" in next_steps_text

    @pytest.mark.asyncio
    async def test_esp32_already_installed_handling(self, mcp_client: Client):
        """Test proper handling when ESP32 core is already installed"""

        print("\n🔄 Testing ESP32 already installed scenario...")

        with patch('src.mcp_arduino_server.components.arduino_board.asyncio.create_subprocess_exec') as mock_create_subprocess:

            # Mock index update (successful)
            mock_index_process = AsyncMock()
            mock_index_process.returncode = 0
            mock_index_process.communicate.return_value = (b"Index updated", b"")

            # Mock core installation (already installed)
            mock_install_process = AsyncMock()
            mock_install_process.returncode = 1  # Non-zero return for already installed
            mock_install_process.wait = AsyncMock()

            # Mock stderr with "already installed" message
            stderr_messages = [
                b"Platform esp32:esp32@2.0.11 already installed\n",
                b""
            ]

            stderr_index = 0
            async def mock_stderr_readline():
                nonlocal stderr_index
                if stderr_index < len(stderr_messages):
                    msg = stderr_messages[stderr_index]
                    stderr_index += 1
                    return msg
                return b""

            mock_stdout = AsyncMock()
            mock_stderr = AsyncMock()
            mock_stdout.readline = AsyncMock(return_value=b"")
            mock_stderr.readline = mock_stderr_readline

            mock_install_process.stdout = mock_stdout
            mock_install_process.stderr = mock_stderr

            def mock_subprocess_factory(*args, **kwargs):
                cmd = args if args else kwargs.get('args', [])
                if any('update-index' in str(arg) for arg in cmd):
                    return mock_index_process
                else:
                    return mock_install_process

            mock_create_subprocess.side_effect = mock_subprocess_factory

            print("📦 Calling arduino_install_esp32 (already installed)...")

            # Execute the ESP32 installation
            result = await mcp_client.call_tool("arduino_install_esp32", {})

            print(f"📊 Already installed result: {result.data}")

            # Verify that "already installed" is handled as success
            assert "success" in result.data
            assert result.data["success"] is True
            assert "already installed" in result.data["message"].lower()

    @pytest.mark.asyncio
    async def test_esp32_installation_timeout_handling(self, mcp_client: Client):
        """Test proper timeout handling for large ESP32 downloads"""

        print("\n⏱️ Testing ESP32 installation timeout handling...")

        with patch('src.mcp_arduino_server.components.arduino_board.asyncio.create_subprocess_exec') as mock_create_subprocess:

            # Mock index update (successful)
            mock_index_process = AsyncMock()
            mock_index_process.returncode = 0
            mock_index_process.communicate.return_value = (b"Index updated", b"")

            # Mock core installation that times out
            mock_install_process = AsyncMock()
            mock_install_process.wait.side_effect = asyncio.TimeoutError()
            mock_install_process.kill = AsyncMock()

            # Mock streams
            mock_stdout = AsyncMock()
            mock_stderr = AsyncMock()
            mock_stdout.readline = AsyncMock(return_value=b"Downloading large package...\n")
            mock_stderr.readline = AsyncMock(return_value=b"")

            mock_install_process.stdout = mock_stdout
            mock_install_process.stderr = mock_stderr

            def mock_subprocess_factory(*args, **kwargs):
                cmd = args if args else kwargs.get('args', [])
                if any('update-index' in str(arg) for arg in cmd):
                    return mock_index_process
                else:
                    return mock_install_process

            mock_create_subprocess.side_effect = mock_subprocess_factory

            print("📦 Calling arduino_install_esp32 (timeout scenario)...")

            # Execute the ESP32 installation
            result = await mcp_client.call_tool("arduino_install_esp32", {})

            print(f"📊 Timeout result: {result.data}")

            # Verify timeout is handled gracefully
            assert "error" in result.data
            assert "timed out" in result.data["error"].lower()
            assert "hint" in result.data

    @pytest.mark.asyncio
    async def test_board_detection_after_esp32_install(self, mcp_client: Client):
        """Test board detection workflow after ESP32 installation"""

        print("\n🔍 Testing board detection after ESP32 installation...")

        # First mock successful ESP32 installation
        with patch('asyncio.create_subprocess_exec') as mock_create_subprocess, \
             patch('src.mcp_arduino_server.components.arduino_board.subprocess.run') as mock_subprocess_run:

            # Mock ESP32 installation processes
            mock_index_process = AsyncMock()
            mock_index_process.returncode = 0
            mock_index_process.communicate.return_value = (b"Index updated", b"")

            mock_install_process = AsyncMock()
            mock_install_process.returncode = 0
            mock_install_process.wait = AsyncMock()

            # Mock successful installation output
            mock_stdout = AsyncMock()
            mock_stderr = AsyncMock()
            mock_stdout.readline = AsyncMock(return_value=b"Platform esp32:esp32@2.0.11 installed\n")
            mock_stderr.readline = AsyncMock(return_value=b"")

            mock_install_process.stdout = mock_stdout
            mock_install_process.stderr = mock_stderr

            def mock_subprocess_factory(*args, **kwargs):
                cmd = args if args else kwargs.get('args', [])
                if any('update-index' in str(arg) for arg in cmd):
                    return mock_index_process
                else:
                    return mock_install_process

            mock_create_subprocess.side_effect = mock_subprocess_factory

            # Mock ESP32 board detection on /dev/ttyUSB0
            esp32_board_detection = {
                "detected_ports": [
                    {
                        "port": {
                            "address": "/dev/ttyUSB0",
                            "protocol": "serial",
                            "label": "/dev/ttyUSB0",
                            "hardware_id": "USB VID:PID=10C4:EA60"
                        },
                        "matching_boards": [
                            {
                                "name": "ESP32 Dev Module",
                                "fqbn": "esp32:esp32:esp32"
                            }
                        ]
                    }
                ]
            }

            def mock_run_side_effect(*args, **kwargs):
                cmd = args[0] if args else []
                mock_result = Mock()
                mock_result.returncode = 0

                if 'board' in cmd and 'list' in cmd:
                    # Board detection command
                    mock_result.stdout = json.dumps(esp32_board_detection)
                elif 'listall' in cmd and 'esp32' in cmd:
                    # Available ESP32 boards command
                    mock_result.stdout = (
                        "ESP32 Dev Module esp32:esp32:esp32\n"
                        "ESP32 Wrover Module esp32:esp32:esp32wrover\n"
                    )
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_subprocess_run.side_effect = mock_run_side_effect

            print("📦 Installing ESP32 core...")

            # Step 1: Install ESP32
            install_result = await mcp_client.call_tool("arduino_install_esp32", {})
            assert install_result.data["success"] is True

            print("✅ ESP32 installation successful")
            print("🔍 Testing board detection...")

            # Step 2: Test board detection
            boards_result = await mcp_client.call_tool("arduino_list_boards", {})

            print(f"📊 Board detection result: {boards_result.data}")

            # Verify ESP32 board is detected on /dev/ttyUSB0
            boards_text = boards_result.data
            assert isinstance(boards_text, str)
            assert "Found 1 connected board" in boards_text
            assert "/dev/ttyUSB0" in boards_text
            assert "ESP32 Dev Module" in boards_text
            assert "esp32:esp32:esp32" in boards_text

    @pytest.mark.asyncio
    async def test_complete_esp32_workflow_integration(self, mcp_client: Client):
        """Test complete ESP32 workflow: install -> list cores -> detect boards"""

        print("\n🔄 Testing complete ESP32 workflow integration...")

        with patch('asyncio.create_subprocess_exec') as mock_create_subprocess, \
             patch('src.mcp_arduino_server.components.arduino_board.subprocess.run') as mock_subprocess_run:

            # Mock ESP32 installation
            mock_index_process = AsyncMock()
            mock_index_process.returncode = 0
            mock_index_process.communicate.return_value = (b"Index updated", b"")

            mock_install_process = AsyncMock()
            mock_install_process.returncode = 0
            mock_install_process.wait = AsyncMock()

            mock_stdout = AsyncMock()
            mock_stderr = AsyncMock()
            mock_stdout.readline = AsyncMock(return_value=b"Platform esp32:esp32@2.0.11 installed\n")
            mock_stderr.readline = AsyncMock(return_value=b"")

            mock_install_process.stdout = mock_stdout
            mock_install_process.stderr = mock_stderr

            def mock_subprocess_factory(*args, **kwargs):
                cmd = args if args else kwargs.get('args', [])
                if any('update-index' in str(arg) for arg in cmd):
                    return mock_index_process
                else:
                    return mock_install_process

            mock_create_subprocess.side_effect = mock_subprocess_factory

            # Mock various arduino-cli commands
            def mock_run_side_effect(*args, **kwargs):
                cmd = args[0] if args else []
                mock_result = Mock()
                mock_result.returncode = 0

                if 'board' in cmd and 'list' in cmd and '--format' in cmd and 'json' in cmd:
                    # Board detection
                    board_data = {
                        "detected_ports": [
                            {
                                "port": {
                                    "address": "/dev/ttyUSB0",
                                    "protocol": "serial",
                                    "label": "/dev/ttyUSB0"
                                },
                                "matching_boards": [
                                    {
                                        "name": "ESP32 Dev Module",
                                        "fqbn": "esp32:esp32:esp32"
                                    }
                                ]
                            }
                        ]
                    }
                    mock_result.stdout = json.dumps(board_data)

                elif 'core' in cmd and 'list' in cmd and '--format' in cmd and 'json' in cmd:
                    # Core listing
                    core_data = {
                        "platforms": [
                            {
                                "id": "esp32:esp32",
                                "installed": "2.0.11",
                                "latest": "2.0.11",
                                "name": "ESP32 Arduino",
                                "maintainer": "Espressif Systems",
                                "website": "https://github.com/espressif/arduino-esp32",
                                "boards": [
                                    {"name": "ESP32 Dev Module"},
                                    {"name": "ESP32 Wrover Module"},
                                    {"name": "ESP32-S2 Saola 1M"},
                                ]
                            }
                        ]
                    }
                    mock_result.stdout = json.dumps(core_data)

                elif 'listall' in cmd and 'esp32' in cmd:
                    # Available ESP32 boards
                    mock_result.stdout = (
                        "ESP32 Dev Module esp32:esp32:esp32\n"
                        "ESP32 Wrover Module esp32:esp32:esp32wrover\n"
                    )
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_subprocess_run.side_effect = mock_run_side_effect

            print("📦 Step 1: Installing ESP32 core...")

            # Step 1: Install ESP32 core
            install_result = await mcp_client.call_tool("arduino_install_esp32", {})
            assert install_result.data["success"] is True
            assert "ESP32 core installed successfully" in install_result.data["message"]

            print("✅ ESP32 core installed")
            print("📋 Step 2: Listing installed cores...")

            # Step 2: Verify ESP32 core is listed
            cores_result = await mcp_client.call_tool("arduino_list_cores", {})
            print(f"📊 Cores result: {cores_result.data}")

            assert cores_result.data["success"] is True
            assert cores_result.data["count"] >= 1

            # Find ESP32 core in the list
            esp32_core = next(
                (core for core in cores_result.data["cores"] if core["id"] == "esp32:esp32"),
                None
            )
            assert esp32_core is not None, f"ESP32 core not found in: {cores_result.data['cores']}"
            assert esp32_core["name"] == "ESP32 Arduino"
            assert esp32_core["maintainer"] == "Espressif Systems"
            assert "ESP32 Dev Module" in [board for board in esp32_core["boards"]]

            print("✅ ESP32 core properly listed")
            print("🔍 Step 3: Detecting connected boards...")

            # Step 3: Detect ESP32 board
            boards_result = await mcp_client.call_tool("arduino_list_boards", {})
            print(f"📊 Boards result: {boards_result.data}")

            boards_text = boards_result.data
            assert "Found 1 connected board" in boards_text
            assert "/dev/ttyUSB0" in boards_text
            assert "ESP32 Dev Module" in boards_text
            assert "FQBN: esp32:esp32:esp32" in boards_text

            print("✅ ESP32 board properly detected on /dev/ttyUSB0")
            print("🎉 Complete workflow successful!")

    @pytest.mark.asyncio
    async def test_esp32_index_update_failure(self, mcp_client: Client):
        """Test ESP32 installation when board index update fails"""

        print("\n❌ Testing ESP32 index update failure...")

        with patch('src.mcp_arduino_server.components.arduino_board.asyncio.create_subprocess_exec') as mock_create_subprocess:

            # Mock index update failure
            mock_index_process = AsyncMock()
            mock_index_process.returncode = 1
            mock_index_process.communicate.return_value = (
                b"",
                b"Error updating index: connection timeout"
            )

            mock_create_subprocess.return_value = mock_index_process

            print("📦 Calling arduino_install_esp32 (index failure)...")

            # Call the ESP32 installation tool
            result = await mcp_client.call_tool("arduino_install_esp32", {})

            print(f"📊 Index failure result: {result.data}")

            # Verify index update failure is handled properly
            assert "error" in result.data
            assert "Failed to update board index" in result.data["error"]


if __name__ == "__main__":
    # Run this specific test file
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
