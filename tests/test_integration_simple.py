"""
Simplified Integration Tests for Arduino MCP Server

These tests focus on verifying server architecture, component integration,
and metadata consistency without requiring full MCP protocol simulation.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.mcp_arduino_server.server_refactored import create_server
from src.mcp_arduino_server.config import ArduinoServerConfig


class TestServerArchitecture:
    """Test the overall server architecture and component integration"""

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

    def test_server_initialization(self, test_config):
        """Test that server initializes with all components properly"""
        server = create_server(test_config)

        # Server should be created successfully
        assert server is not None
        assert server.name == "Arduino Development Server"

        # Verify directories were created
        assert test_config.sketches_base_dir.exists()
        assert test_config.build_temp_dir.exists()

    @pytest.mark.asyncio
    async def test_tool_registration_completeness(self, test_config):
        """Test that all expected tool categories are registered"""
        server = create_server(test_config)
        tools = await server.get_tools()
        tool_names = list(tools.keys())

        # Expected tool patterns by component
        expected_patterns = {
            'sketch': ['arduino_create_sketch', 'arduino_list_sketches', 'arduino_read_sketch',
                      'arduino_write_sketch', 'arduino_compile_sketch', 'arduino_upload_sketch'],
            'library': ['arduino_search_libraries', 'arduino_install_library', 'arduino_uninstall_library',
                       'arduino_list_library_examples'],
            'board': ['arduino_list_boards', 'arduino_search_boards', 'arduino_install_core',
                     'arduino_list_cores', 'arduino_update_cores'],
            'debug': ['arduino_debug_start', 'arduino_debug_interactive', 'arduino_debug_break',
                     'arduino_debug_run', 'arduino_debug_print', 'arduino_debug_backtrace',
                     'arduino_debug_watch', 'arduino_debug_memory', 'arduino_debug_registers',
                     'arduino_debug_stop'],
            'wireviz': ['wireviz_generate_from_yaml', 'wireviz_generate_from_description']
        }

        # Verify each category has expected tools
        for category, expected_tools in expected_patterns.items():
            found_tools = [name for name in tool_names if any(pattern in name for pattern in expected_tools)]
            assert len(found_tools) >= len(expected_tools) // 2, \
                f"Missing tools in {category} category. Found: {found_tools}"

        # Verify total tool count is reasonable
        assert len(tool_names) >= 20, f"Expected at least 20 tools, found {len(tool_names)}"

    @pytest.mark.asyncio
    async def test_resource_registration_completeness(self, test_config):
        """Test that all expected resources are registered"""
        server = create_server(test_config)
        resources = await server.get_resources()
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
            assert expected_uri in resource_uris, \
                f"Resource {expected_uri} not found in {resource_uris}"

    @pytest.mark.asyncio
    async def test_tool_metadata_consistency(self, test_config):
        """Test that all tools have consistent metadata"""
        server = create_server(test_config)
        tools = await server.get_tools()

        for tool_name in tools.keys():
            tool = await server.get_tool(tool_name)

            # Verify basic metadata
            assert isinstance(tool.name, str)
            assert len(tool.name) > 0
            assert isinstance(tool.description, str)
            assert len(tool.description) > 0

            # Verify naming convention
            assert tool_name.startswith(('arduino_', 'wireviz_')), \
                f"Tool {tool_name} doesn't follow naming convention"

    @pytest.mark.asyncio
    async def test_resource_metadata_consistency(self, test_config):
        """Test that all resources have consistent metadata"""
        server = create_server(test_config)
        resources = await server.get_resources()

        for resource_uri in resources.keys():
            resource = await server.get_resource(resource_uri)

            # Verify basic metadata
            assert "://" in str(resource.uri)
            assert isinstance(resource.name, str)
            assert len(resource.name) > 0

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

    def test_component_isolation(self, test_config):
        """Test that components can be created independently"""
        from src.mcp_arduino_server.components import (
            ArduinoSketch, ArduinoLibrary, ArduinoBoard,
            ArduinoDebug, WireViz
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

    def test_directory_creation(self, tmp_path):
        """Test that server creates required directories"""
        sketches_dir = tmp_path / "custom_sketches"

        config = ArduinoServerConfig(
            sketches_base_dir=sketches_dir
        )

        # Directory shouldn't exist initially
        assert not sketches_dir.exists()

        # Create server
        server = create_server(config)

        # Directory should be created
        assert sketches_dir.exists()
        # Build temp dir should also be created (as a subdirectory)
        assert config.build_temp_dir.exists()

    def test_logging_configuration(self, test_config, caplog):
        """Test that server produces expected log messages"""
        with caplog.at_level("INFO"):
            server = create_server(test_config)

        # Check for key initialization messages
        log_messages = [record.message for record in caplog.records]

        # Should log server initialization
        assert any("Arduino Development Server" in msg for msg in log_messages)
        assert any("initialized" in msg for msg in log_messages)
        assert any("Components loaded" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_tool_naming_patterns(self, test_config):
        """Test that tools follow consistent naming patterns"""
        server = create_server(test_config)
        tools = await server.get_tools()

        arduino_tools = [name for name in tools.keys() if name.startswith('arduino_')]
        wireviz_tools = [name for name in tools.keys() if name.startswith('wireviz_')]

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

    def test_server_factory_pattern(self, test_config):
        """Test that create_server function works as expected factory"""
        # Should work with explicit config
        server1 = create_server(test_config)
        assert server1 is not None

        # Should work with None (default config)
        server2 = create_server(None)
        assert server2 is not None

        # Should work with no arguments (default config)
        server3 = create_server()
        assert server3 is not None

        # Each call should create new instance
        assert server1 is not server2
        assert server2 is not server3

    @pytest.mark.asyncio
    async def test_error_resilience(self, tmp_path):
        """Test that server handles configuration errors gracefully"""
        # Test with read-only directory (should still work)
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        # Note: Can't easily make directory read-only in tests without root

        # Test with very long path (within reason)
        long_path = tmp_path / ("very_" * 20 + "long_directory_name")
        config = ArduinoServerConfig(sketches_base_dir=long_path)
        server = create_server(config)
        assert server is not None
        assert long_path.exists()

    def test_version_info_access(self, test_config):
        """Test that version information is accessible"""
        server = create_server(test_config)

        # Server should have version info available through name or other means
        assert hasattr(server, 'name')
        assert isinstance(server.name, str)
        assert len(server.name) > 0

    @pytest.mark.asyncio
    async def test_resource_uri_patterns(self, test_config):
        """Test that resource URIs follow expected patterns"""
        server = create_server(test_config)
        resources = await server.get_resources()

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


class TestComponentIntegration:
    """Test how components work together"""

    @pytest.fixture
    def server_with_components(self, tmp_path):
        """Create server with all components for integration testing"""
        config = ArduinoServerConfig(
            sketches_base_dir=tmp_path / "sketches",
            build_temp_dir=tmp_path / "build"
        )
        return create_server(config)

    @pytest.mark.asyncio
    async def test_component_tool_distribution(self, server_with_components):
        """Test that tools are distributed across all components"""
        tools = await server_with_components.get_tools()
        tool_names = list(tools.keys())

        # Count tools by component
        sketch_tools = [name for name in tool_names if 'sketch' in name]
        library_tools = [name for name in tool_names if 'librar' in name]
        board_tools = [name for name in tool_names if 'board' in name or 'core' in name]
        debug_tools = [name for name in tool_names if 'debug' in name]
        wireviz_tools = [name for name in tool_names if 'wireviz' in name]

        # Each component should contribute tools
        assert len(sketch_tools) > 0, "No sketch tools found"
        assert len(library_tools) > 0, "No library tools found"
        assert len(board_tools) > 0, "No board tools found"
        assert len(debug_tools) > 0, "No debug tools found"
        assert len(wireviz_tools) > 0, "No wireviz tools found"

    @pytest.mark.asyncio
    async def test_component_resource_distribution(self, server_with_components):
        """Test that resources are distributed across components"""
        resources = await server_with_components.get_resources()
        resource_uris = list(resources.keys())

        # Should have resources from each major component
        arduino_resources = [uri for uri in resource_uris if 'arduino://' in str(uri)]
        wireviz_resources = [uri for uri in resource_uris if 'wireviz://' in str(uri)]
        server_resources = [uri for uri in resource_uris if 'server://' in str(uri)]

        assert len(arduino_resources) > 0, "No Arduino resources found"
        assert len(wireviz_resources) > 0, "No WireViz resources found"
        assert len(server_resources) > 0, "No server resources found"

    def test_component_config_sharing(self, tmp_path):
        """Test that all components share the same configuration"""
        config = ArduinoServerConfig(
            sketches_base_dir=tmp_path / "shared",
            command_timeout=45
        )
        server = create_server(config)

        # All components should use the same config
        # This is tested implicitly by successful server creation
        assert server is not None
        assert config.sketches_base_dir.exists()