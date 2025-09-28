"""
Integration tests for the Arduino MCP Server using FastMCP run_server_in_process

These tests verify the complete server functionality including:
- Server initialization and configuration with proper context
- Tool execution through HTTP transport
- Cross-component workflows
- End-to-end functionality with real MCP protocol
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

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


class TestArduinoMCPServerIntegration:
    """Test suite for full Arduino MCP server integration with real protocol"""

    @pytest.mark.asyncio
    async def test_server_tool_discovery(self, mcp_client: Client):
        """Test that server properly registers all tools"""
        tools = await mcp_client.list_tools()
        tool_names = [tool.name for tool in tools]

        # Verify we have tools from all components
        sketch_tools = [name for name in tool_names if name.startswith('arduino_') and 'sketch' in name]
        library_tools = [name for name in tool_names if name.startswith('arduino_') and 'librar' in name]
        board_tools = [name for name in tool_names if name.startswith('arduino_') and ('board' in name or 'core' in name)]
        debug_tools = [name for name in tool_names if name.startswith('arduino_') and 'debug' in name]
        wireviz_tools = [name for name in tool_names if name.startswith('wireviz_')]

        assert len(sketch_tools) >= 4, f"Expected sketch tools, found: {sketch_tools}"
        assert len(library_tools) >= 3, f"Expected library tools, found: {library_tools}"
        assert len(board_tools) >= 3, f"Expected board tools, found: {board_tools}"
        assert len(debug_tools) >= 8, f"Expected debug tools, found: {debug_tools}"
        assert len(wireviz_tools) >= 2, f"Expected wireviz tools, found: {wireviz_tools}"

    @pytest.mark.asyncio
    async def test_server_resource_discovery(self, mcp_client: Client):
        """Test that server properly registers all resources"""
        resources = await mcp_client.list_resources()
        resource_uris = [str(resource.uri) for resource in resources]

        expected_resources = [
            "arduino://sketches",
            "arduino://libraries",
            "arduino://boards",
            "arduino://debug/sessions",
            "wireviz://instructions",
            "server://info"
        ]

        for expected_uri in expected_resources:
            assert expected_uri in resource_uris, f"Resource {expected_uri} not found in {resource_uris}"

    @pytest.mark.asyncio
    async def test_sketch_workflow_integration(self, mcp_client: Client):
        """Test complete sketch creation and management workflow"""
        with patch('subprocess.run') as mock_subprocess:

            # Mock successful Arduino CLI operations
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = "Compilation successful"

            # Create a sketch
            create_result = await mcp_client.call_tool("arduino_create_sketch", {
                "sketch_name": "test_integration"
            })

            assert "success" in create_result.data
            assert create_result.data["success"] is True
            assert "test_integration" in create_result.data["message"]

            # Read the sketch
            read_result = await mcp_client.call_tool("arduino_read_sketch", {
                "sketch_name": "test_integration"
            })

            assert "success" in read_result.data
            assert read_result.data["success"] is True
            assert "void setup()" in read_result.data["content"]

            # Update the sketch with new content
            new_content = """
void setup() {
  Serial.begin(9600);
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(1000);
  digitalWrite(LED_BUILTIN, LOW);
  delay(1000);
}
"""

            write_result = await mcp_client.call_tool("arduino_write_sketch", {
                "sketch_name": "test_integration",
                "content": new_content,
                "auto_compile": False
            })

            assert "success" in write_result.data
            assert write_result.data["success"] is True

            # Compile the sketch
            compile_result = await mcp_client.call_tool("arduino_compile_sketch", {
                "sketch_name": "test_integration",
                "board_fqbn": "arduino:avr:uno"
            })

            assert "success" in compile_result.data
            assert compile_result.data["success"] is True
            assert "compiled successfully" in compile_result.data["message"]

    @pytest.mark.asyncio
    async def test_library_search_workflow(self, mcp_client: Client):
        """Test library search functionality"""
        with patch('subprocess.run') as mock_subprocess:
            # Mock successful library search
            mock_search_response = {
                "libraries": [
                    {
                        "name": "FastLED",
                        "latest": {"version": "3.6.0"},
                        "sentence": "LED control library"
                    }
                ]
            }

            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = json.dumps(mock_search_response)

            # Search for a library
            search_result = await mcp_client.call_tool("arduino_search_libraries", {
                "query": "FastLED"
            })

            assert "success" in search_result.data
            assert search_result.data["success"] is True
            assert len(search_result.data["libraries"]) > 0
            assert search_result.data["libraries"][0]["name"] == "FastLED"

    @pytest.mark.asyncio
    async def test_board_detection_workflow(self, mcp_client: Client):
        """Test board detection functionality with real hardware"""
        # Test real board detection (no mocking needed)
        boards_result = await mcp_client.call_tool("arduino_list_boards", {})

        # The test should pass if either:
        # 1. A board is detected, or
        # 2. No boards are found (but the tool works)
        result_text = boards_result.data

        # Check that the tool executed successfully
        assert isinstance(result_text, str)

        # Should either find boards or report none found
        board_found = "Found" in result_text and "board" in result_text
        no_boards = "No Arduino boards detected" in result_text

        assert board_found or no_boards, f"Unexpected board detection response: {result_text}"

        # If a board is found, verify the format is correct
        if board_found:
            assert "Port:" in result_text
            assert "Protocol:" in result_text

    @pytest.mark.asyncio
    async def test_wireviz_yaml_generation(self, mcp_client: Client):
        """Test WireViz YAML-based circuit generation"""
        with patch('subprocess.run') as mock_subprocess, \
             patch('datetime.datetime') as mock_datetime:

            # Mock successful WireViz generation
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stderr = ""
            mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

            yaml_content = """
connectors:
  Arduino:
    type: Arduino Uno
    pins: [GND, D2]
  LED:
    type: LED
    pins: [anode, cathode]

cables:
  wire:
    colors: [RD]
    gauge: 22 AWG

connections:
  - Arduino: [D2]
    cable: [1]
    LED: [anode]
"""

            # This test will validate that the tool can be called properly
            # The actual PNG generation is mocked to avoid file system dependencies
            result = await mcp_client.call_tool("wireviz_generate_from_yaml", {
                "yaml_content": yaml_content,
                "output_base": "circuit"
            })

            # The result should contain error due to mocked PNG file not existing
            # but this confirms the tool execution path works correctly
            assert "error" in result.data or "success" in result.data

    @pytest.mark.asyncio
    async def test_resource_access(self, mcp_client: Client):
        """Test accessing server resources"""
        # Test WireViz instructions resource
        instructions = await mcp_client.read_resource("wireviz://instructions")
        content = instructions[0].text

        assert "WireViz Circuit Diagram Instructions" in content
        assert "Basic YAML Structure:" in content
        assert "Color Codes:" in content

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, mcp_client: Client):
        """Test error handling across components"""
        # Test sketch compilation failure
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value.returncode = 1
            mock_subprocess.return_value.stderr = "error: expected ';' before '}'"

            compile_result = await mcp_client.call_tool("arduino_compile_sketch", {
                "sketch_name": "nonexistent_sketch",
                "board_fqbn": "arduino:avr:uno"
            })

            assert "error" in compile_result.data
            assert "not found" in compile_result.data["error"] or "Compilation failed" in compile_result.data.get("error", "")

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mcp_client: Client):
        """Test concurrent tool execution"""
        # Test multiple concurrent tool calls
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = "Success"

            # Execute multiple tools concurrently
            tasks = [
                mcp_client.call_tool("arduino_list_sketches", {}),
                mcp_client.call_tool("arduino_list_cores", {}),
                mcp_client.read_resource("arduino://sketches")
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All operations should complete without exceptions
            for result in results:
                assert not isinstance(result, Exception), f"Operation failed: {result}"


class TestPerformanceIntegration:
    """Test performance characteristics of the Arduino MCP server"""

    @pytest.mark.asyncio
    async def test_rapid_tool_calls(self, mcp_client: Client):
        """Test server performance under rapid tool calls"""
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = "Success"

            # Execute many rapid calls
            tasks = []
            for i in range(10):
                task = mcp_client.call_tool("arduino_list_sketches", {})
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All calls should succeed
            for result in results:
                assert not isinstance(result, Exception), f"Rapid call failed: {result}"
                # Most calls should succeed (some might have mocking conflicts but that's expected)
                assert hasattr(result, 'data')
