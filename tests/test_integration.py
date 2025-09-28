"""
Integration tests for the Arduino MCP Server (cleaned version)

These tests verify server architecture and component integration
without requiring full MCP protocol simulation.
"""


import pytest

from src.mcp_arduino_server.config import ArduinoServerConfig
from src.mcp_arduino_server.server_refactored import create_server


class TestServerIntegration:
    """Test suite for server architecture integration"""

    @pytest.fixture
    def test_config(self, tmp_path):
        """Create test configuration with temporary directories"""
        return ArduinoServerConfig(
            arduino_cli_path="/usr/bin/arduino-cli",
            sketches_base_dir=tmp_path / "sketches",
            build_temp_dir=tmp_path / "build",
            wireviz_path="/usr/bin/wireviz",
            command_timeout=30,
            enable_client_sampling=True
        )

    @pytest.fixture
    def mcp_server(self, test_config):
        """Create a test MCP server instance"""
        return create_server(test_config)

    def test_server_creation(self, test_config):
        """Test that server creates successfully with all components"""
        server = create_server(test_config)

        assert server is not None
        assert server.name == "Arduino Development Server"

        # Verify directories were created
        assert test_config.sketches_base_dir.exists()
        assert test_config.build_temp_dir.exists()

    @pytest.mark.asyncio
    async def test_server_tools_registration(self, mcp_server):
        """Test that all expected tools are registered"""
        # Get all registered tools
        tools = await mcp_server.get_tools()
        tool_names = list(tools.keys())

        # Verify sketch tools
        sketch_tools = [name for name in tool_names if name.startswith('arduino_') and 'sketch' in name]
        assert len(sketch_tools) >= 5  # create, list, read, write, compile, upload

        # Verify library tools
        library_tools = [name for name in tool_names if 'librar' in name]
        assert len(library_tools) >= 3  # search, install, list examples

        # Verify board tools
        board_tools = [name for name in tool_names if 'board' in name or 'core' in name]
        assert len(board_tools) >= 4  # list boards, search boards, install core, list cores

        # Verify debug tools
        debug_tools = [name for name in tool_names if 'debug' in name]
        assert len(debug_tools) >= 5  # start, interactive, break, run, print, etc.

        # Verify WireViz tools
        wireviz_tools = [name for name in tool_names if 'wireviz' in name]
        assert len(wireviz_tools) >= 2  # generate from yaml, generate from description

    @pytest.mark.asyncio
    async def test_server_resources_registration(self, mcp_server):
        """Test that all expected resources are registered"""
        # Get all registered resources
        resources = await mcp_server.get_resources()
        resource_uris = list(resources.keys())

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
    async def test_server_info_resource(self, mcp_server):
        """Test the server info resource provides correct information"""
        # Get the server info resource
        info_resource = await mcp_server.get_resource("server://info")
        info_content = await info_resource.read()

        assert "Arduino Development Server" in info_content
        assert "Configuration:" in info_content
        assert "Components:" in info_content
        assert "Available Tool Categories:" in info_content
        assert "Sketch Tools:" in info_content
        assert "Library Tools:" in info_content
        assert "Board Tools:" in info_content
        assert "Debug Tools:" in info_content
        assert "WireViz Tools:" in info_content

    def test_component_isolation(self, test_config):
        """Test that components can be created independently"""
        from src.mcp_arduino_server.components import (
            ArduinoBoard,
            ArduinoDebug,
            ArduinoLibrary,
            ArduinoSketch,
            WireViz,
        )

        # Each component should initialize without errors
        sketch = ArduinoSketch(test_config)
        library = ArduinoLibrary(test_config)
        board = ArduinoBoard(test_config)
        debug = ArduinoDebug(test_config)
        wireviz = WireViz(test_config)

        # Components should have expected attributes
        assert hasattr(sketch, 'config')
        assert hasattr(library, 'config')
        assert hasattr(board, 'config')
        assert hasattr(debug, 'config')
        assert hasattr(wireviz, 'config')

    def test_configuration_flexibility(self, tmp_path):
        """Test that server handles various configuration scenarios"""
        # Test minimal configuration
        minimal_config = ArduinoServerConfig(
            sketches_base_dir=tmp_path / "minimal"
        )
        server1 = create_server(minimal_config)
        assert server1 is not None

        # Test custom configuration
        custom_config = ArduinoServerConfig(
            arduino_cli_path="/custom/arduino-cli",
            wireviz_path="/custom/wireviz",
            sketches_base_dir=tmp_path / "custom",
            command_timeout=60,
            enable_client_sampling=False
        )
        server2 = create_server(custom_config)
        assert server2 is not None

        # Test that different configs create distinct servers
        assert server1 is not server2

    @pytest.mark.asyncio
    async def test_tool_naming_consistency(self, mcp_server):
        """Test that tools follow consistent naming patterns"""
        tools = await mcp_server.get_tools()
        tool_names = list(tools.keys())

        arduino_tools = [name for name in tool_names if name.startswith('arduino_')]
        wireviz_tools = [name for name in tool_names if name.startswith('wireviz_')]

        # Should have both Arduino and WireViz tools
        assert len(arduino_tools) > 0, "No Arduino tools found"
        assert len(wireviz_tools) > 0, "No WireViz tools found"

        # Arduino tools should follow patterns
        for tool_name in arduino_tools:
            # Should have component_action pattern
            parts = tool_name.split('_')
            assert len(parts) >= 2, f"Arduino tool {tool_name} doesn't follow naming pattern"
            assert parts[0] == 'arduino'

        # WireViz tools should follow patterns
        for tool_name in wireviz_tools:
            parts = tool_name.split('_')
            assert len(parts) >= 2, f"WireViz tool {tool_name} doesn't follow naming pattern"
            assert parts[0] == 'wireviz'

    @pytest.mark.asyncio
    async def test_resource_uri_patterns(self, mcp_server):
        """Test that resource URIs follow expected patterns"""
        resources = await mcp_server.get_resources()

        # Group by scheme
        schemes = {}
        for uri in resources.keys():
            scheme = str(uri).split('://')[0]
            if scheme not in schemes:
                schemes[scheme] = []
            schemes[scheme].append(uri)

        # Should have expected schemes
        assert 'arduino' in schemes, "No arduino:// resources found"
        assert 'wireviz' in schemes, "No wireviz:// resources found"
        assert 'server' in schemes, "No server:// resources found"

        # Each scheme should have reasonable number of resources
        assert len(schemes['arduino']) >= 3, "Too few arduino:// resources"
        assert len(schemes['wireviz']) >= 1, "Too few wireviz:// resources"
        assert len(schemes['server']) >= 1, "Too few server:// resources"
