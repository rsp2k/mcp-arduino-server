"""
Tests for ArduinoLibrary component
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import assert_logged_info, assert_progress_reported


class TestArduinoLibrary:
    """Test suite for ArduinoLibrary component"""

    @pytest.mark.asyncio
    async def test_search_libraries_success(self, library_component, test_context, mock_arduino_cli):
        """Test successful library search"""
        # Setup mock response
        mock_response = {
            "libraries": [
                {
                    "name": "Servo",
                    "author": "Arduino",
                    "sentence": "Control servo motors",
                    "paragraph": "Detailed description",
                    "category": "Device Control",
                    "architectures": ["*"],
                    "latest": {"version": "1.1.8"}
                },
                {
                    "name": "WiFi",
                    "author": "Arduino",
                    "sentence": "WiFi connectivity",
                    "paragraph": "WiFi library",
                    "category": "Communication",
                    "architectures": ["esp32"],
                    "latest": {"version": "2.0.0"}
                }
            ]
        }
        mock_arduino_cli.return_value.stdout = json.dumps(mock_response)
        mock_arduino_cli.return_value.returncode = 0

        result = await library_component.search_libraries(
            test_context,
            "servo",
            limit=5
        )

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["libraries"]) == 2
        assert result["libraries"][0]["name"] == "Servo"

        # Verify arduino-cli was called correctly
        mock_arduino_cli.assert_called_once()
        call_args = mock_arduino_cli.call_args[0][0]
        assert "lib" in call_args
        assert "search" in call_args
        assert "servo" in call_args

    @pytest.mark.asyncio
    async def test_search_libraries_empty(self, library_component, test_context, mock_arduino_cli):
        """Test library search with no results"""
        mock_arduino_cli.return_value.stdout = '{"libraries": []}'
        mock_arduino_cli.return_value.returncode = 0

        result = await library_component.search_libraries(
            test_context,
            "nonexistent"
        )

        assert result["count"] == 0
        assert result["libraries"] == []
        assert "No libraries found" in result["message"]

    @pytest.mark.asyncio
    async def test_search_libraries_limit(self, library_component, test_context, mock_arduino_cli):
        """Test library search respects limit"""
        # Create mock response with many libraries
        libraries = [
            {
                "name": f"Library{i}",
                "author": "Test",
                "latest": {"version": "1.0.0"}
            }
            for i in range(20)
        ]
        mock_arduino_cli.return_value.stdout = json.dumps({"libraries": libraries})
        mock_arduino_cli.return_value.returncode = 0

        result = await library_component.search_libraries(
            test_context,
            "test",
            limit=5
        )

        assert result["count"] == 5
        assert len(result["libraries"]) == 5

    @pytest.mark.asyncio
    async def test_install_library_success(self, library_component, test_context, mock_async_subprocess):
        """Test successful library installation with progress"""
        # Mock the async subprocess for progress tracking
        mock_process = mock_async_subprocess.return_value
        mock_process.returncode = 0

        # Simulate progress output
        mock_process.stdout.readline = AsyncMock(side_effect=[
            b'Downloading Servo@1.1.8...\n',
            b'Installing Servo@1.1.8...\n',
            b'Servo@1.1.8 installed\n',
            b''  # End of stream
        ])
        mock_process.wait = AsyncMock(return_value=0)

        result = await library_component.install_library(
            test_context,
            "Servo"
        )

        assert result["success"] is True
        assert "installed successfully" in result["message"]

        # Verify progress was reported
        assert_progress_reported(test_context, min_calls=2)
        assert_logged_info(test_context, "Starting installation")

    @pytest.mark.asyncio
    async def test_install_library_with_version(self, library_component, test_context, mock_async_subprocess):
        """Test installing specific library version"""
        mock_process = mock_async_subprocess.return_value
        mock_process.returncode = 0
        mock_process.stdout.readline = AsyncMock(return_value=b'')
        mock_process.wait = AsyncMock(return_value=0)

        result = await library_component.install_library(
            test_context,
            "WiFi",
            "2.0.0"
        )

        assert result["success"] is True

        # Verify version was included in command
        call_args = mock_async_subprocess.call_args[0]
        assert "@2.0.0" in call_args

    @pytest.mark.asyncio
    async def test_install_library_already_installed(self, library_component, test_context, mock_async_subprocess):
        """Test installing library that's already installed"""
        mock_process = mock_async_subprocess.return_value
        mock_process.returncode = 1

        # Simulate the stderr output for already installed
        mock_process.stderr.readline = AsyncMock(side_effect=[
            b'Library already installed\n',
            b''
        ])
        mock_process.stdout.readline = AsyncMock(return_value=b'')
        mock_process.wait = AsyncMock(return_value=1)

        result = await library_component.install_library(
            test_context,
            "ExistingLib"
        )

        assert result["success"] is True
        assert "already installed" in result["message"]

    @pytest.mark.asyncio
    async def test_uninstall_library_success(self, library_component, test_context, mock_arduino_cli):
        """Test successful library uninstallation"""
        mock_arduino_cli.return_value.returncode = 0
        mock_arduino_cli.return_value.stdout = "Library uninstalled"

        result = await library_component.uninstall_library(
            test_context,
            "OldLibrary"
        )

        assert result["success"] is True
        assert "uninstalled successfully" in result["message"]

        # Verify command
        call_args = mock_arduino_cli.call_args[0][0]
        assert "lib" in call_args
        assert "uninstall" in call_args
        assert "OldLibrary" in call_args

    @pytest.mark.asyncio
    async def test_list_library_examples_found(self, library_component, test_context, temp_dir):
        """Test listing examples from installed library"""
        # Create library directory structure
        lib_dir = temp_dir / "Arduino" / "libraries" / "TestLib"
        lib_dir.mkdir(parents=True)

        examples_dir = lib_dir / "examples"
        examples_dir.mkdir()

        # Create example sketches
        example1 = examples_dir / "Basic"
        example1.mkdir()
        (example1 / "Basic.ino").write_text("// Basic example\nvoid setup() {}")

        example2 = examples_dir / "Advanced"
        example2.mkdir()
        (example2 / "Advanced.ino").write_text("// Advanced example\n// With multiple features\nvoid setup() {}")

        # Update component's arduino_user_dir
        library_component.arduino_user_dir = temp_dir / "Arduino"

        result = await library_component.list_library_examples(
            test_context,
            "TestLib"
        )

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["examples"]) == 2

        # Check example details
        example_names = [ex["name"] for ex in result["examples"]]
        assert "Basic" in example_names
        assert "Advanced" in example_names

    @pytest.mark.asyncio
    async def test_list_library_examples_not_found(self, library_component, test_context, temp_dir):
        """Test listing examples for non-existent library"""
        # Create the libraries directory but no library
        lib_dir = temp_dir / "Arduino" / "libraries"
        lib_dir.mkdir(parents=True)

        library_component.arduino_user_dir = temp_dir / "Arduino"

        result = await library_component.list_library_examples(
            test_context,
            "NonExistentLib"
        )

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_list_library_examples_no_examples(self, library_component, test_context, temp_dir):
        """Test library with no examples"""
        # Create library without examples directory
        lib_dir = temp_dir / "Arduino" / "libraries" / "NoExamplesLib"
        lib_dir.mkdir(parents=True)

        library_component.arduino_user_dir = temp_dir / "Arduino"

        result = await library_component.list_library_examples(
            test_context,
            "NoExamplesLib"
        )

        assert result["message"] == "Library 'NoExamplesLib' has no examples"
        assert result["examples"] == []

    @pytest.mark.asyncio
    async def test_list_library_examples_fuzzy_match(self, library_component, test_context, temp_dir):
        """Test fuzzy matching for library names"""
        # Create library with slightly different name
        lib_dir = temp_dir / "Arduino" / "libraries" / "ServoMotor"
        lib_dir.mkdir(parents=True)
        examples_dir = lib_dir / "examples"
        examples_dir.mkdir()

        example = examples_dir / "Sweep"
        example.mkdir()
        (example / "Sweep.ino").write_text("// Sweep example")

        library_component.arduino_user_dir = temp_dir / "Arduino"

        # Enable fuzzy matching
        library_component.fuzzy_available = True
        library_component.fuzz = MagicMock()
        library_component.fuzz.ratio = MagicMock(return_value=85)  # High similarity score

        result = await library_component.list_library_examples(
            test_context,
            "Servo"  # Close but not exact match
        )

        # With fuzzy matching, it should find ServoMotor
        assert result["success"] is True
        assert result["library"] == "ServoMotor"
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_get_installed_libraries(self, library_component, mock_arduino_cli):
        """Test getting list of installed libraries"""
        mock_response = {
            "installed_libraries": [
                {
                    "name": "Servo",
                    "version": "1.1.8",
                    "author": "Arduino",
                    "sentence": "Control servo motors"
                }
            ]
        }
        mock_arduino_cli.return_value.stdout = json.dumps(mock_response)
        mock_arduino_cli.return_value.returncode = 0

        # Call the private method directly
        libraries = await library_component._get_installed_libraries()

        assert len(libraries) == 1
        assert libraries[0]["name"] == "Servo"

    @pytest.mark.asyncio
    async def test_list_installed_libraries_resource(self, library_component, mock_arduino_cli):
        """Test the MCP resource for listing installed libraries"""
        mock_response = {
            "installed_libraries": [
                {
                    "name": "WiFi",
                    "version": "2.0.0",
                    "author": "Arduino",
                    "sentence": "Connect to WiFi networks"
                },
                {
                    "name": "SPI",
                    "version": "1.0.0",
                    "author": "Arduino",
                    "sentence": "SPI communication"
                }
            ]
        }
        mock_arduino_cli.return_value.stdout = json.dumps(mock_response)
        mock_arduino_cli.return_value.returncode = 0

        result = await library_component.list_installed_libraries()

        assert "Installed Arduino Libraries (2)" in result
        assert "WiFi" in result
        assert "SPI" in result

    def test_get_example_description(self, library_component, temp_dir):
        """Test extracting description from example file"""
        # Test single-line comment
        ino_file = temp_dir / "test.ino"
        ino_file.write_text("// This is a test example\nvoid setup() {}")

        description = library_component._get_example_description(ino_file)
        assert description == "This is a test example"

        # Test multi-line comment - it finds the first non-star line
        ino_file.write_text("/*\n * Multi-line\n * Example description\n */\nvoid setup() {}")
        description = library_component._get_example_description(ino_file)
        assert description == "Multi-line"  # It returns the first non-star content

        # Test no description
        ino_file.write_text("void setup() {}")
        description = library_component._get_example_description(ino_file)
        assert description == "No description available"

    @pytest.mark.asyncio
    async def test_install_library_timeout(self, library_component, test_context, mock_async_subprocess):
        """Test library installation timeout handling"""
        mock_process = mock_async_subprocess.return_value

        # Simulate timeout
        async def timeout_side_effect():
            raise asyncio.TimeoutError()

        mock_process.wait = timeout_side_effect

        # Mock readline to prevent hanging
        mock_process.stdout.readline = AsyncMock(return_value=b'')
        mock_process.stderr.readline = AsyncMock(return_value=b'')

        result = await library_component.install_library(
            test_context,
            "SlowLibrary"
        )

        assert "error" in result
        assert "timed out" in result["error"]
