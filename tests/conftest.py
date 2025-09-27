"""
Pytest configuration and fixtures for mcp-arduino-server tests
"""
import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, AsyncMock, patch

import pytest
from fastmcp import Context
from fastmcp.utilities.tests import run_server_in_process

from mcp_arduino_server.config import ArduinoServerConfig
from mcp_arduino_server.components import (
    ArduinoSketch,
    ArduinoLibrary,
    ArduinoBoard,
    ArduinoDebug,
    WireViz
)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_config(temp_dir: Path) -> ArduinoServerConfig:
    """Create a test configuration with temporary directories"""
    config = ArduinoServerConfig(
        sketches_base_dir=temp_dir / "sketches",
        build_temp_dir=temp_dir / "build",
        arduino_cli_path="arduino-cli",  # Will be mocked
        wireviz_path="wireviz",  # Will be mocked
        enable_client_sampling=True
    )
    # Ensure directories exist
    config.sketches_base_dir.mkdir(parents=True, exist_ok=True)
    config.build_temp_dir.mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def mock_arduino_cli():
    """Mock arduino-cli subprocess calls"""
    with patch('subprocess.run') as mock_run:
        # Default successful response
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"success": true}'
        mock_run.return_value.stderr = ''
        yield mock_run


@pytest.fixture
def mock_async_subprocess():
    """Mock async subprocess for components that use it"""
    with patch('asyncio.create_subprocess_exec') as mock_exec:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        mock_process.stdin = AsyncMock()

        # Mock readline for progress monitoring
        mock_process.stdout.readline = AsyncMock(
            side_effect=[
                b'Downloading core...\n',
                b'Installing core...\n',
                b'Core installed successfully\n',
                b''  # End of stream
            ]
        )
        mock_process.stderr.readline = AsyncMock(return_value=b'')
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.communicate = AsyncMock(return_value=(b'Success', b''))

        mock_exec.return_value = mock_process
        yield mock_exec


@pytest.fixture
def test_context():
    """Create a test context with mocked elicitation support"""
    # Create a mock context object
    ctx = Mock(spec=Context)

    # Add elicitation methods for interactive debugging tests
    ctx.ask_user = AsyncMock(return_value="Continue to next breakpoint")
    ctx.ask_confirmation = AsyncMock(return_value=True)

    # Track progress and log calls for assertions
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()

    # Add sampling support for AI features
    ctx.sample = AsyncMock(return_value=Mock(
        choices=[Mock(
            message=Mock(
                content="Generated YAML content"
            )
        )]
    ))

    return ctx


@pytest.fixture
def sketch_component(test_config: ArduinoServerConfig) -> ArduinoSketch:
    """Create ArduinoSketch component instance"""
    return ArduinoSketch(test_config)


@pytest.fixture
def library_component(test_config: ArduinoServerConfig) -> ArduinoLibrary:
    """Create ArduinoLibrary component instance"""
    return ArduinoLibrary(test_config)


@pytest.fixture
def board_component(test_config: ArduinoServerConfig) -> ArduinoBoard:
    """Create ArduinoBoard component instance"""
    return ArduinoBoard(test_config)


@pytest.fixture
def debug_component(test_config: ArduinoServerConfig) -> ArduinoDebug:
    """Create ArduinoDebug component instance"""
    return ArduinoDebug(test_config)


@pytest.fixture
def wireviz_component(test_config: ArduinoServerConfig) -> WireViz:
    """Create WireViz component instance"""
    return WireViz(test_config)


@pytest.fixture
def sample_sketch_content() -> str:
    """Sample Arduino sketch code"""
    return """// Blink LED
void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(1000);
    digitalWrite(LED_BUILTIN, LOW);
    delay(1000);
}
"""


@pytest.fixture
def sample_wireviz_yaml() -> str:
    """Sample WireViz YAML configuration"""
    return """
connectors:
  Arduino:
    type: Arduino Uno
    pins: [GND, D13]
  LED:
    type: LED
    pins: [cathode, anode]
cables:
  jumper:
    colors: [BK, RD]
connections:
  - Arduino: [GND]
    cable: [1]
    LED: [cathode]
  - Arduino: [D13]
    cable: [2]
    LED: [anode]
"""


@pytest.fixture
def mock_board_list_response() -> str:
    """Mock JSON response for board list"""
    return """{
    "detected_ports": [
        {
            "port": {
                "address": "/dev/ttyUSB0",
                "protocol": "serial",
                "label": "Arduino Uno"
            },
            "matching_boards": [
                {
                    "name": "Arduino Uno",
                    "fqbn": "arduino:avr:uno"
                }
            ]
        }
    ]
}"""


@pytest.fixture
def mock_library_search_response() -> str:
    """Mock JSON response for library search"""
    return """{
    "libraries": [
        {
            "name": "Servo",
            "author": "Arduino",
            "sentence": "Allows Arduino boards to control servo motors",
            "paragraph": "This library can control a great number of servos.",
            "category": "Device Control",
            "architectures": ["*"],
            "latest": {
                "version": "1.1.8"
            }
        }
    ]
}"""


# Helper functions for testing

def create_sketch_directory(base_dir: Path, sketch_name: str, content: str = None) -> Path:
    """Helper to create a sketch directory with .ino file"""
    sketch_dir = base_dir / sketch_name
    sketch_dir.mkdir(parents=True, exist_ok=True)
    ino_file = sketch_dir / f"{sketch_name}.ino"

    if content is None:
        content = f"// {sketch_name}\nvoid setup() {{}}\nvoid loop() {{}}"

    ino_file.write_text(content)
    return sketch_dir


def assert_progress_reported(ctx: Mock, min_calls: int = 1):
    """Assert that progress was reported at least min_calls times"""
    assert ctx.report_progress.call_count >= min_calls, \
        f"Expected at least {min_calls} progress reports, got {ctx.report_progress.call_count}"


def assert_logged_info(ctx: Mock, message_fragment: str):
    """Assert that an info message containing the fragment was logged"""
    for call in ctx.info.call_args_list:
        if message_fragment in str(call):
            return
    assert False, f"Info message containing '{message_fragment}' not found in logs"