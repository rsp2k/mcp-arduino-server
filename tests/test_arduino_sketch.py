"""
Tests for ArduinoSketch component
"""
from unittest.mock import patch

import pytest

from tests.conftest import create_sketch_directory


class TestArduinoSketch:
    """Test suite for ArduinoSketch component"""

    @pytest.mark.asyncio
    async def test_create_sketch_success(self, sketch_component, test_context, temp_dir):
        """Test successful sketch creation"""
        # Mock the file opening to prevent actual file opening during tests
        with patch.object(sketch_component, '_open_file'):
            result = await sketch_component.create_sketch(
                ctx=test_context,
                sketch_name="TestSketch"
            )

        assert result["success"] is True
        assert "TestSketch" in result["message"]

        # Verify sketch directory was created
        sketch_dir = temp_dir / "sketches" / "TestSketch"
        assert sketch_dir.exists()

        # Verify .ino file was created with boilerplate
        ino_file = sketch_dir / "TestSketch.ino"
        assert ino_file.exists()
        content = ino_file.read_text()
        assert "void setup()" in content
        assert "void loop()" in content

    @pytest.mark.asyncio
    async def test_create_sketch_already_exists(self, sketch_component, test_context, temp_dir):
        """Test creating a sketch that already exists"""
        # Mock the file opening to prevent actual file opening during tests
        with patch.object(sketch_component, '_open_file'):
            # Create sketch first time
            await sketch_component.create_sketch(test_context, "DuplicateSketch")

            # Try to create again
            result = await sketch_component.create_sketch(test_context, "DuplicateSketch")

            assert "error" in result
            assert "already exists" in result["error"]

    @pytest.mark.asyncio
    async def test_create_sketch_invalid_name(self, sketch_component, test_context):
        """Test creating sketch with invalid name"""
        invalid_names = ["../hack", "sketch/name", "sketch\\name", ".", ".."]

        for invalid_name in invalid_names:
            result = await sketch_component.create_sketch(test_context, invalid_name)
            assert "error" in result
            assert "Invalid sketch name" in result["error"]

    @pytest.mark.asyncio
    async def test_list_sketches_empty(self, sketch_component, test_context):
        """Test listing sketches when none exist"""
        result = await sketch_component.list_sketches(test_context)

        assert "No Arduino sketches found" in result

    @pytest.mark.asyncio
    async def test_list_sketches_multiple(self, sketch_component, test_context, temp_dir):
        """Test listing multiple sketches"""
        # Create several sketches
        sketch_names = ["Blink", "Servo", "Temperature"]
        for name in sketch_names:
            create_sketch_directory(temp_dir / "sketches", name)

        result = await sketch_component.list_sketches(test_context)

        assert f"Found {len(sketch_names)} Arduino sketch(es)" in result
        for name in sketch_names:
            assert name in result

    @pytest.mark.asyncio
    async def test_read_sketch_success(self, sketch_component, test_context, temp_dir, sample_sketch_content):
        """Test reading sketch content"""
        # Create a sketch
        sketch_dir = create_sketch_directory(
            temp_dir / "sketches",
            "ReadTest",
            sample_sketch_content
        )

        result = await sketch_component.read_sketch(
            test_context,
            "ReadTest"
        )

        assert result["success"] is True
        assert result["content"] == sample_sketch_content
        assert result["lines"] == len(sample_sketch_content.splitlines())

    @pytest.mark.asyncio
    async def test_read_sketch_not_found(self, sketch_component, test_context):
        """Test reading non-existent sketch"""
        result = await sketch_component.read_sketch(
            test_context,
            "NonExistent"
        )

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_write_sketch_new(self, sketch_component, test_context, temp_dir, sample_sketch_content):
        """Test writing a new sketch file"""
        result = await sketch_component.write_sketch(
            test_context,
            "NewSketch",
            sample_sketch_content,
            auto_compile=False  # Skip compilation for test
        )

        assert result["success"] is True
        assert result["lines"] == len(sample_sketch_content.splitlines())

        # Verify file was written
        ino_file = temp_dir / "sketches" / "NewSketch" / "NewSketch.ino"
        assert ino_file.exists()
        assert ino_file.read_text() == sample_sketch_content

    @pytest.mark.asyncio
    async def test_write_sketch_update(self, sketch_component, test_context, temp_dir):
        """Test updating existing sketch"""
        # Create initial sketch
        sketch_dir = create_sketch_directory(
            temp_dir / "sketches",
            "UpdateTest",
            "// Original content"
        )

        # Update with new content
        new_content = "// Updated content\nvoid setup() {}\nvoid loop() {}"
        result = await sketch_component.write_sketch(
            test_context,
            "UpdateTest",
            new_content,
            auto_compile=False
        )

        assert result["success"] is True

        # Verify update
        ino_file = sketch_dir / "UpdateTest.ino"
        assert ino_file.read_text() == new_content

    @pytest.mark.asyncio
    async def test_compile_sketch_success(self, sketch_component, test_context, temp_dir, mock_arduino_cli):
        """Test successful sketch compilation"""
        # Setup mock response
        mock_arduino_cli.return_value.returncode = 0
        mock_arduino_cli.return_value.stdout = "Compilation successful"

        # Create sketch
        create_sketch_directory(temp_dir / "sketches", "CompileTest")

        result = await sketch_component.compile_sketch(
            test_context,
            "CompileTest"
        )

        assert result["success"] is True
        assert "compiled successfully" in result["message"]

        # Verify arduino-cli was called correctly
        mock_arduino_cli.assert_called_once()
        call_args = mock_arduino_cli.call_args[0][0]
        assert "compile" in call_args
        assert "--fqbn" in call_args

    @pytest.mark.asyncio
    async def test_compile_sketch_failure(self, sketch_component, test_context, temp_dir, mock_arduino_cli):
        """Test compilation failure"""
        # Setup mock response
        mock_arduino_cli.return_value.returncode = 1
        mock_arduino_cli.return_value.stderr = "error: expected ';' before '}'"

        create_sketch_directory(temp_dir / "sketches", "BadSketch")

        result = await sketch_component.compile_sketch(
            test_context,
            "BadSketch"
        )

        assert "error" in result
        assert "Compilation failed" in result["error"]
        assert "expected ';'" in result["stderr"]

    @pytest.mark.asyncio
    async def test_upload_sketch_success(self, sketch_component, test_context, temp_dir, mock_arduino_cli):
        """Test successful sketch upload"""
        # Setup mock response
        mock_arduino_cli.return_value.returncode = 0
        mock_arduino_cli.return_value.stdout = "Upload complete"

        create_sketch_directory(temp_dir / "sketches", "UploadTest")

        result = await sketch_component.upload_sketch(
            test_context,
            "UploadTest",
            "/dev/ttyUSB0"
        )

        assert result["success"] is True
        assert "uploaded successfully" in result["message"]
        assert result["port"] == "/dev/ttyUSB0"

        # Verify arduino-cli was called with upload
        call_args = mock_arduino_cli.call_args[0][0]
        assert "upload" in call_args
        assert "--port" in call_args
        assert "/dev/ttyUSB0" in call_args

    @pytest.mark.asyncio
    async def test_upload_sketch_port_error(self, sketch_component, test_context, temp_dir, mock_arduino_cli):
        """Test upload failure due to port issues"""
        # Setup mock response
        mock_arduino_cli.return_value.returncode = 1
        mock_arduino_cli.return_value.stderr = "can't open device '/dev/ttyUSB0': Permission denied"

        create_sketch_directory(temp_dir / "sketches", "PortTest")

        result = await sketch_component.upload_sketch(
            test_context,
            "PortTest",
            "/dev/ttyUSB0"
        )

        assert "error" in result
        assert "Upload failed" in result["error"]
        assert "Permission denied" in result["stderr"]

    @pytest.mark.asyncio
    async def test_write_with_auto_compile(self, sketch_component, test_context, temp_dir, mock_arduino_cli):
        """Test write with auto-compilation enabled"""
        # Setup successful compilation
        mock_arduino_cli.return_value.returncode = 0
        mock_arduino_cli.return_value.stdout = "Compilation successful"

        result = await sketch_component.write_sketch(
            test_context,
            "AutoCompile",
            "void setup() {}\nvoid loop() {}",
            auto_compile=True
        )

        assert result["success"] is True
        assert "compilation" in result

        # Verify compilation was triggered
        mock_arduino_cli.assert_called_once()
        call_args = mock_arduino_cli.call_args[0][0]
        assert "compile" in call_args

    @pytest.mark.asyncio
    async def test_list_sketches_resource(self, sketch_component, temp_dir):
        """Test the MCP resource for listing sketches"""
        # Create some sketches
        create_sketch_directory(temp_dir / "sketches", "Resource1")
        create_sketch_directory(temp_dir / "sketches", "Resource2")

        # Call the resource method directly
        result = await sketch_component.list_sketches_resource()

        assert "Found 2 Arduino sketch(es)" in result
        assert "Resource1" in result
        assert "Resource2" in result

    @pytest.mark.asyncio
    async def test_read_additional_file(self, sketch_component, test_context, temp_dir):
        """Test reading additional files in sketch directory"""
        # Create sketch with additional header file
        sketch_dir = create_sketch_directory(temp_dir / "sketches", "MultiFile")
        header_file = sketch_dir / "config.h"
        header_content = "#define PIN_LED 13"
        header_file.write_text(header_content)

        result = await sketch_component.read_sketch(
            test_context,
            "MultiFile",
            "config.h"
        )

        assert result["success"] is True
        assert result["content"] == header_content

    @pytest.mark.asyncio
    async def test_write_disallowed_extension(self, sketch_component, test_context):
        """Test writing file with disallowed extension"""
        result = await sketch_component.write_sketch(
            test_context,
            "BadExt",
            "malicious content",
            file_name="hack.exe",
            auto_compile=False
        )

        assert "error" in result
        assert "not allowed" in result["error"]
