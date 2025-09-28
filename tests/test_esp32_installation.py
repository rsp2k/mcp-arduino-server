"""Test ESP32 core installation functionality"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastmcp import Context

from mcp_arduino_server.components.arduino_board import ArduinoBoard
from mcp_arduino_server.config import ArduinoServerConfig


@pytest.mark.asyncio
async def test_install_esp32_success():
    """Test successful ESP32 core installation"""
    config = ArduinoServerConfig()
    board = ArduinoBoard(config)

    # Create mock context
    ctx = Mock(spec=Context)
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.error = AsyncMock()
    ctx.report_progress = AsyncMock()

    # Mock subprocess for index update
    update_process = AsyncMock()
    update_process.returncode = 0
    update_process.communicate = AsyncMock(return_value=(b"Index updated", b""))

    # Mock subprocess for core installation
    install_process = AsyncMock()
    install_process.returncode = 0
    install_process.stdout.readline = AsyncMock(side_effect=[
        b"Downloading esp32:esp32-arduino-libs@3.0.0\n",
        b"Installing esp32:esp32@3.0.0\n",
        b"Platform esp32:esp32@3.0.0 installed\n",
        b""  # End of stream
    ])
    install_process.stderr.readline = AsyncMock(return_value=b"")
    install_process.wait = AsyncMock(return_value=0)

    # Mock board list subprocess
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="ESP32 Dev Module esp32:esp32:esp32",
            stderr=""
        )

        with patch('asyncio.create_subprocess_exec', side_effect=[update_process, install_process]):
            with patch('asyncio.wait_for', side_effect=[
                (b"Index updated", b""),  # For index update
                0  # For installation wait
            ]):
                result = await board.install_esp32(ctx)

    # Verify successful installation
    assert result["success"] is True
    assert "ESP32 core installed successfully" in result["message"]
    assert "next_steps" in result

    # Verify progress reporting
    ctx.report_progress.assert_called()
    ctx.info.assert_called()

    # Verify ESP32 URL was used
    calls = ctx.debug.call_args_list
    assert any("https://raw.githubusercontent.com/espressif/arduino-esp32" in str(call)
              for call in calls)


@pytest.mark.asyncio
async def test_install_esp32_already_installed():
    """Test ESP32 installation when already installed"""
    config = ArduinoServerConfig()
    board = ArduinoBoard(config)

    ctx = Mock(spec=Context)
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.error = AsyncMock()
    ctx.report_progress = AsyncMock()

    # Mock index update success
    update_process = AsyncMock()
    update_process.returncode = 0
    update_process.communicate = AsyncMock(return_value=(b"", b""))

    # Mock installation with "already installed" message
    install_process = AsyncMock()
    install_process.returncode = 1
    install_process.stdout.readline = AsyncMock(return_value=b"")
    install_process.stderr.readline = AsyncMock(side_effect=[
        b"Platform esp32:esp32 already installed\n",
        b""
    ])
    install_process.wait = AsyncMock(return_value=1)

    with patch('asyncio.create_subprocess_exec', side_effect=[update_process, install_process]):
        with patch('asyncio.wait_for', side_effect=[
            (b"", b""),  # For index update
            1  # For installation wait
        ]):
            result = await board.install_esp32(ctx)

    # Should still be successful when already installed
    assert result["success"] is True
    assert "already installed" in result["message"].lower()


@pytest.mark.asyncio
async def test_install_esp32_timeout():
    """Test ESP32 installation timeout handling"""
    config = ArduinoServerConfig()
    board = ArduinoBoard(config)

    ctx = Mock(spec=Context)
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.error = AsyncMock()
    ctx.report_progress = AsyncMock()

    # Mock index update success
    update_process = AsyncMock()
    update_process.returncode = 0
    update_process.communicate = AsyncMock(return_value=(b"", b""))

    # Mock installation process
    install_process = AsyncMock()
    install_process.stdout.readline = AsyncMock(side_effect=[
        b"Downloading large package...\n",
        b""  # End of stream
    ])
    install_process.stderr.readline = AsyncMock(return_value=b"")
    install_process.kill = Mock()

    with patch('asyncio.create_subprocess_exec', side_effect=[update_process, install_process]):
        with patch('asyncio.wait_for', side_effect=[
            (b"", b""),  # For index update
            asyncio.TimeoutError()  # For installation
        ]):
            result = await board.install_esp32(ctx)

    # Verify timeout handling
    assert "error" in result
    assert "timed out" in result["error"].lower()
    assert "hint" in result
    install_process.kill.assert_called_once()
    ctx.error.assert_called()


@pytest.mark.asyncio
async def test_install_esp32_index_update_failure():
    """Test ESP32 installation when index update fails"""
    config = ArduinoServerConfig()
    board = ArduinoBoard(config)

    ctx = Mock(spec=Context)
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.error = AsyncMock()
    ctx.report_progress = AsyncMock()

    # Mock index update failure
    update_process = AsyncMock()
    update_process.returncode = 1
    update_process.communicate = AsyncMock(return_value=(b"", b"Network error"))

    with patch('asyncio.create_subprocess_exec', return_value=update_process):
        with patch('asyncio.wait_for', return_value=(b"", b"Network error")):
            result = await board.install_esp32(ctx)

    # Verify index update failure handling
    assert "error" in result
    assert "Failed to update board index" in result["error"]
    ctx.error.assert_called()


@pytest.mark.asyncio
async def test_install_esp32_progress_tracking():
    """Test that ESP32 installation properly tracks and reports progress"""
    config = ArduinoServerConfig()
    board = ArduinoBoard(config)

    ctx = Mock(spec=Context)
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.error = AsyncMock()
    ctx.report_progress = AsyncMock()

    # Mock successful index update
    update_process = AsyncMock()
    update_process.returncode = 0
    update_process.communicate = AsyncMock(return_value=(b"", b""))

    # Mock installation with various progress messages
    install_process = AsyncMock()
    install_process.returncode = 0

    # Simulate progressive download messages
    messages = [
        b"Downloading esp32:esp32-arduino-libs@3.0.0 (425MB)\n",
        b"Downloading esp32:esp-rv32@2411 (566MB)\n",
        b"Installing esp32:esp32@3.0.0\n",
        b"Platform esp32:esp32@3.0.0 installed\n",
        b""  # End of stream
    ]

    install_process.stdout.readline = AsyncMock(side_effect=messages)
    install_process.stderr.readline = AsyncMock(return_value=b"")
    install_process.wait = AsyncMock(return_value=0)

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch('asyncio.create_subprocess_exec', side_effect=[update_process, install_process]):
            with patch('asyncio.wait_for', side_effect=[
                (b"", b""),  # For index update
                0  # For installation
            ]):
                result = await board.install_esp32(ctx)

    # Verify progress was tracked
    assert result["success"] is True

    # Check that progress was reported multiple times
    progress_calls = ctx.report_progress.call_args_list
    assert len(progress_calls) >= 4  # At least initial, download, install, complete

    # Verify progress values increase
    progress_values = [call[0][0] for call in progress_calls]
    assert progress_values == sorted(progress_values)  # Should be monotonically increasing
    assert progress_values[-1] == 100  # Should end at 100%


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
