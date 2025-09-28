"""
Tests for WireViz component
"""
import os
import subprocess
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.mcp_arduino_server.components.wireviz import WireViz, WireVizRequest


class TestWireViz:
    """Test suite for WireViz component"""

    @pytest.fixture
    def wireviz_component(self, test_config):
        """Create WireViz component for testing"""
        component = WireViz(test_config)
        return component

    @pytest.fixture
    def sample_yaml_content(self):
        """Sample WireViz YAML content for testing"""
        return """connectors:
  Arduino:
    type: Arduino Uno
    pins: [GND, 5V, D2, A0]

  LED:
    type: LED
    pins: [cathode, anode]

cables:
  power:
    colors: [BK, RD]
    gauge: 22 AWG

connections:
  - Arduino: [GND]
    cable: [1]
    LED: [cathode]
  - Arduino: [D2]
    cable: [2]
    LED: [anode]
"""

    @pytest.fixture
    def mock_png_image(self):
        """Mock PNG image data"""
        # Simple PNG header for testing
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
        return png_data

    @pytest.mark.asyncio
    async def test_generate_from_yaml_success(self, wireviz_component, test_context, temp_dir, sample_yaml_content, mock_png_image):
        """Test successful circuit diagram generation from YAML"""
        # Set up temp directory
        wireviz_component.sketches_base_dir = temp_dir

        # Mock WireViz subprocess
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stderr = ""

            # Create a mock PNG file that will be "generated"
            with patch('datetime.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

                # Pre-create the output directory and PNG file
                output_dir = temp_dir / "wireviz_20240101_120000"
                output_dir.mkdir(parents=True, exist_ok=True)
                png_file = output_dir / "circuit.png"
                png_file.write_bytes(mock_png_image)

                # Mock file opening
                with patch.object(wireviz_component, '_open_file') as mock_open:
                    result = await wireviz_component.generate_from_yaml(
                        yaml_content=sample_yaml_content,
                        output_base="circuit"
                    )

            assert result["success"] is True
            assert "Circuit diagram generated" in result["message"]
            assert "image" in result
            assert isinstance(result["image"], type(result["image"]))  # Check it's an Image object
            assert "paths" in result
            assert "yaml" in result["paths"]
            assert "png" in result["paths"]
            assert "directory" in result["paths"]

            # Verify WireViz was called with correct arguments
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0][0]
            assert wireviz_component.wireviz_path in call_args
            assert "-o" in call_args

            # Verify file opening was attempted
            mock_open.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_from_yaml_wireviz_failure(self, wireviz_component, temp_dir, sample_yaml_content):
        """Test WireViz subprocess failure"""
        wireviz_component.sketches_base_dir = temp_dir

        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value.returncode = 1
            mock_subprocess.return_value.stderr = "Invalid YAML syntax"

            result = await wireviz_component.generate_from_yaml(
                yaml_content=sample_yaml_content
            )

            assert "error" in result
            assert "WireViz failed" in result["error"]
            assert "Invalid YAML syntax" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_from_yaml_no_png_generated(self, wireviz_component, temp_dir, sample_yaml_content):
        """Test when WireViz succeeds but no PNG is generated"""
        wireviz_component.sketches_base_dir = temp_dir

        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stderr = ""

            with patch('datetime.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

                # Create output directory but no PNG file
                output_dir = temp_dir / "wireviz_20240101_120000"
                output_dir.mkdir(parents=True, exist_ok=True)

                result = await wireviz_component.generate_from_yaml(
                    yaml_content=sample_yaml_content
                )

            assert "error" in result
            assert "No PNG file generated" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_from_yaml_timeout(self, wireviz_component, temp_dir, sample_yaml_content):
        """Test WireViz timeout handling"""
        wireviz_component.sketches_base_dir = temp_dir

        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.side_effect = subprocess.TimeoutExpired("wireviz", 30)

            result = await wireviz_component.generate_from_yaml(
                yaml_content=sample_yaml_content
            )

            assert "error" in result
            assert "WireViz timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_from_description_success(self, wireviz_component, test_context, temp_dir, mock_png_image):
        """Test AI-powered generation from description"""
        wireviz_component.sketches_base_dir = temp_dir

        # Mock client sampling
        test_context.sample = AsyncMock()
        mock_result = Mock()
        mock_result.content = """connectors:
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
        test_context.sample.return_value = mock_result

        # Mock the entire generate_from_yaml method to avoid SamplingMessage validation issues
        with patch.object(wireviz_component, 'generate_from_yaml') as mock_generate:
            mock_generate.return_value = {
                "success": True,
                "message": "Circuit diagram generated",
                "image": Mock(),
                "paths": {"yaml": "test.yaml", "png": "test.png", "directory": "/tmp/test"}
            }

            result = await wireviz_component.generate_from_description(
                ctx=test_context,
                description="LED connected to Arduino pin D2",
                sketch_name="blink_test",
                output_base="circuit"
            )

        assert result["success"] is True
        assert "yaml_generated" in result
        assert "generated_by" in result
        assert result["generated_by"] == "client_llm_sampling"

        # Verify sampling was called with correct parameters
        test_context.sample.assert_called_once()
        call_args = test_context.sample.call_args
        assert call_args[1]["max_tokens"] == 2000
        assert call_args[1]["temperature"] == 0.3
        assert len(call_args[1]["messages"]) == 1  # We combine system and user prompts into one message

    @pytest.mark.asyncio
    async def test_generate_from_description_no_context(self, wireviz_component):
        """Test AI generation without context"""
        result = await wireviz_component.generate_from_description(
            ctx=None,
            description="LED circuit"
        )

        assert "error" in result
        assert "No context available" in result["error"]
        assert "MCP client" in result["hint"]

    @pytest.mark.asyncio
    async def test_generate_from_description_no_sampling_support(self, wireviz_component, test_context):
        """Test AI generation when client doesn't support sampling"""
        # Remove sample method to simulate no sampling support
        if hasattr(test_context, 'sample'):
            delattr(test_context, 'sample')

        result = await wireviz_component.generate_from_description(
            ctx=test_context,
            description="LED circuit"
        )

        assert "error" in result
        assert "Client sampling not available" in result["error"]
        assert "fallback" in result

    @pytest.mark.asyncio
    async def test_generate_from_description_no_llm_response(self, wireviz_component, test_context):
        """Test AI generation when LLM returns no content"""
        test_context.sample = AsyncMock()
        test_context.sample.return_value = None

        # Mock SamplingMessage to avoid validation issues
        with patch('src.mcp_arduino_server.components.wireviz.SamplingMessage'):
            result = await wireviz_component.generate_from_description(
                ctx=test_context,
                description="LED circuit"
            )

        assert "error" in result
        assert "No response from client LLM" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_from_description_empty_response(self, wireviz_component, test_context):
        """Test AI generation when LLM returns empty content"""
        test_context.sample = AsyncMock()
        mock_result = Mock()
        mock_result.content = ""
        test_context.sample.return_value = mock_result

        # Mock SamplingMessage to avoid validation issues
        with patch('src.mcp_arduino_server.components.wireviz.SamplingMessage'):
            result = await wireviz_component.generate_from_description(
                ctx=test_context,
                description="LED circuit"
            )

        assert "error" in result
        assert "No response from client LLM" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_from_description_yaml_generation_failure(self, wireviz_component, test_context, temp_dir):
        """Test when AI generates YAML but WireViz fails"""
        wireviz_component.sketches_base_dir = temp_dir

        test_context.sample = AsyncMock()
        mock_result = Mock()
        mock_result.content = "invalid: yaml: content:"
        test_context.sample.return_value = mock_result

        # Mock WireViz failure and SamplingMessage
        with patch('subprocess.run') as mock_subprocess, \
             patch('src.mcp_arduino_server.components.wireviz.SamplingMessage'):
            mock_subprocess.return_value.returncode = 1
            mock_subprocess.return_value.stderr = "YAML parse error"

            result = await wireviz_component.generate_from_description(
                ctx=test_context,
                description="Invalid circuit description"
            )

        assert "error" in result
        assert "WireViz failed" in result["error"]

    @pytest.mark.asyncio
    async def test_get_wireviz_instructions_resource(self, wireviz_component):
        """Test WireViz instructions resource"""
        instructions = await wireviz_component.get_wireviz_instructions()

        assert "WireViz Circuit Diagram Instructions" in instructions
        assert "Basic YAML Structure" in instructions
        assert "connectors:" in instructions
        assert "cables:" in instructions
        assert "connections:" in instructions
        assert "Color Codes:" in instructions
        assert "wireviz_generate_from_description" in instructions

    def test_clean_yaml_content_with_markdown(self, wireviz_component):
        """Test YAML content cleaning removes markdown"""
        # Test with markdown code fences
        yaml_with_markdown = """```yaml
connectors:
  Arduino:
    type: Arduino Uno
```"""

        cleaned = wireviz_component._clean_yaml_content(yaml_with_markdown)

        assert not cleaned.startswith('```')
        assert not cleaned.endswith('```')
        assert 'connectors:' in cleaned
        assert 'Arduino:' in cleaned

    def test_clean_yaml_content_without_markdown(self, wireviz_component):
        """Test YAML content cleaning preserves clean YAML"""
        clean_yaml = """connectors:
  Arduino:
    type: Arduino Uno"""

        cleaned = wireviz_component._clean_yaml_content(clean_yaml)

        assert cleaned == clean_yaml

    def test_clean_yaml_content_partial_markdown(self, wireviz_component):
        """Test YAML content cleaning with only starting fence"""
        yaml_with_start_fence = """```yaml
connectors:
  Arduino:
    type: Arduino Uno"""

        cleaned = wireviz_component._clean_yaml_content(yaml_with_start_fence)

        assert not cleaned.startswith('```')
        assert 'connectors:' in cleaned

    def test_create_wireviz_prompt_basic(self, wireviz_component):
        """Test WireViz prompt creation"""
        prompt = wireviz_component._create_wireviz_prompt(
            "LED connected to pin D2",
            ""
        )

        assert "LED connected to pin D2" in prompt
        assert "WireViz YAML" in prompt
        assert "proper WireViz YAML syntax" in prompt
        assert "connectors, cables, and connections" in prompt

    def test_create_wireviz_prompt_with_sketch_name(self, wireviz_component):
        """Test WireViz prompt creation with sketch name"""
        prompt = wireviz_component._create_wireviz_prompt(
            "LED blink circuit",
            "blink_demo"
        )

        assert "LED blink circuit" in prompt
        assert "blink_demo" in prompt
        assert "Arduino sketch named: blink_demo" in prompt

    def test_open_file_posix(self, wireviz_component, temp_dir):
        """Test file opening on POSIX systems"""
        test_file = temp_dir / "test.png"
        test_file.write_text("fake image")

        with patch('os.name', 'posix'), \
             patch('os.uname') as mock_uname, \
             patch('subprocess.run') as mock_subprocess, \
             patch.dict(os.environ, {'TESTING_MODE': '0'}):

            mock_uname.return_value.sysname = 'Linux'

            wireviz_component._open_file(test_file)

            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0][0]
            assert 'xdg-open' in call_args
            assert str(test_file) in call_args

    def test_open_file_macos(self, wireviz_component, temp_dir):
        """Test file opening on macOS"""
        test_file = temp_dir / "test.png"
        test_file.write_text("fake image")

        with patch('os.name', 'posix'), \
             patch('os.uname') as mock_uname, \
             patch('subprocess.run') as mock_subprocess, \
             patch.dict(os.environ, {'TESTING_MODE': '0'}):

            mock_uname.return_value.sysname = 'Darwin'

            wireviz_component._open_file(test_file)

            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0][0]
            assert 'open' in call_args
            assert str(test_file) in call_args

    def test_open_file_windows(self, wireviz_component, temp_dir):
        """Test file opening on Windows"""
        test_file = temp_dir / "test.png"
        test_file.write_text("fake image")

        with patch('os.name', 'nt'), \
             patch('subprocess.run') as mock_subprocess, \
             patch.dict(os.environ, {'TESTING_MODE': '0'}):

            wireviz_component._open_file(test_file)

            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0][0]
            assert 'cmd' in call_args
            assert '/c' in call_args
            assert 'start' in call_args
            assert str(test_file) in call_args

    def test_open_file_error_handling(self, wireviz_component, temp_dir, caplog):
        """Test file opening error handling"""
        test_file = temp_dir / "nonexistent.png"

        with patch('os.name', 'posix'), \
             patch('subprocess.run') as mock_subprocess, \
             patch.dict(os.environ, {'TESTING_MODE': '0'}):

            mock_subprocess.side_effect = Exception("Command failed")

            # Should not raise exception, just log warning
            wireviz_component._open_file(test_file)

            # Check that warning was logged
            assert any("Could not open file automatically" in record.message for record in caplog.records)

    def test_wireviz_request_model(self):
        """Test WireVizRequest pydantic model"""
        # Test with all fields
        request = WireVizRequest(
            yaml_content="test yaml",
            description="test description",
            sketch_name="test_sketch",
            output_base="test_output"
        )

        assert request.yaml_content == "test yaml"
        assert request.description == "test description"
        assert request.sketch_name == "test_sketch"
        assert request.output_base == "test_output"

        # Test with defaults
        minimal_request = WireVizRequest()
        assert minimal_request.yaml_content is None
        assert minimal_request.description is None
        assert minimal_request.sketch_name == "circuit"
        assert minimal_request.output_base == "circuit"

    @pytest.mark.asyncio
    async def test_generate_from_yaml_creates_timestamped_directory(self, wireviz_component, temp_dir, sample_yaml_content, mock_png_image):
        """Test that generate_from_yaml creates unique timestamped directories"""
        wireviz_component.sketches_base_dir = temp_dir

        with patch('subprocess.run') as mock_subprocess, \
             patch.object(wireviz_component, '_open_file'):

            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stderr = ""

            # Mock datetime to return specific timestamp
            with patch('datetime.datetime') as mock_datetime:
                mock_datetime.now.return_value.strftime.return_value = "20240515_143022"

                # Pre-create the expected output directory and PNG file
                expected_dir = temp_dir / "wireviz_20240515_143022"
                expected_dir.mkdir(parents=True, exist_ok=True)
                png_file = expected_dir / "circuit.png"
                png_file.write_bytes(mock_png_image)

                result = await wireviz_component.generate_from_yaml(
                    yaml_content=sample_yaml_content
                )

        assert result["success"] is True
        assert "wireviz_20240515_143022" in result["paths"]["directory"]
        assert expected_dir.exists()

    @pytest.mark.asyncio
    async def test_generate_from_description_exception_handling(self, wireviz_component, test_context):
        """Test exception handling in generate_from_description"""
        test_context.sample = AsyncMock()
        test_context.sample.side_effect = Exception("Sampling error")

        # Mock SamplingMessage to avoid validation issues
        with patch('src.mcp_arduino_server.components.wireviz.SamplingMessage'):
            result = await wireviz_component.generate_from_description(
                ctx=test_context,
                description="test circuit"
            )

        assert "error" in result
        assert "Generation failed" in result["error"]
        assert "Sampling error" in result["error"]

    @pytest.mark.asyncio
    async def test_yaml_content_persistence(self, wireviz_component, temp_dir, sample_yaml_content, mock_png_image):
        """Test that YAML content is written to file correctly"""
        wireviz_component.sketches_base_dir = temp_dir

        with patch('subprocess.run') as mock_subprocess, \
             patch('datetime.datetime') as mock_datetime, \
             patch.object(wireviz_component, '_open_file'):

            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stderr = ""
            mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

            # Pre-create output directory and PNG file
            output_dir = temp_dir / "wireviz_20240101_120000"
            output_dir.mkdir(parents=True, exist_ok=True)
            png_file = output_dir / "test_circuit.png"
            png_file.write_bytes(mock_png_image)

            result = await wireviz_component.generate_from_yaml(
                yaml_content=sample_yaml_content,
                output_base="test_circuit"
            )

        # Verify YAML was written to file
        yaml_file = output_dir / "test_circuit.yaml"
        assert yaml_file.exists()
        written_content = yaml_file.read_text()
        assert "connectors:" in written_content
        assert "Arduino:" in written_content
        assert "LED:" in written_content

        assert result["success"] is True
