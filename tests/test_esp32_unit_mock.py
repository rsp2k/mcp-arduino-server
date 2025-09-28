"""
ESP32 Installation Unit Tests with Proper Mocking
==================================================

This test file validates the ESP32 installation functionality using direct
component testing with comprehensive mocking.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastmcp import Context

from src.mcp_arduino_server.components.arduino_board import ArduinoBoard
from src.mcp_arduino_server.config import ArduinoServerConfig


class TestESP32InstallationUnit:
    """Unit tests for ESP32 installation functionality"""

    @pytest.fixture
    def config(self):
        """Create test configuration"""
        return ArduinoServerConfig(
            arduino_cli_path="/usr/bin/arduino-cli",
            command_timeout=30
        )

    @pytest.fixture
    def arduino_board(self, config):
        """Create ArduinoBoard component instance"""
        return ArduinoBoard(config)

    @pytest.fixture
    def mock_context(self):
        """Create mock FastMCP context"""
        ctx = Mock(spec=Context)
        ctx.info = AsyncMock()
        ctx.debug = AsyncMock()
        ctx.error = AsyncMock()
        ctx.report_progress = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_esp32_install_successful(self, arduino_board, mock_context):
        """Test successful ESP32 installation"""
        print("\n🔧 Testing successful ESP32 installation...")

        # Mock index update process
        mock_index_process = AsyncMock()
        mock_index_process.returncode = 0
        mock_index_process.communicate.return_value = (
            b"Updating index: package_index.json downloaded",
            b""
        )

        # Mock core installation process
        mock_install_process = AsyncMock()
        mock_install_process.returncode = 0
        mock_install_process.wait = AsyncMock()

        # Create progressive output simulation
        stdout_messages = [
            b"Downloading esp32:esp32@2.0.11...\n",
            b"esp32:esp32@2.0.11 downloaded\n",
            b"Downloading xtensa-esp32-elf-gcc@8.4.0+2021r2-patch5...\n",
            b"Installing esp32:esp32@2.0.11...\n",
            b"Platform esp32:esp32@2.0.11 installed\n",
            b""  # End of stream
        ]

        message_index = 0
        async def mock_stdout_readline():
            nonlocal message_index
            if message_index < len(stdout_messages):
                msg = stdout_messages[message_index]
                message_index += 1
                await asyncio.sleep(0.01)  # Simulate some delay
                return msg
            return b""

        mock_install_process.stdout = AsyncMock()
        mock_install_process.stderr = AsyncMock()
        mock_install_process.stdout.readline = mock_stdout_readline
        mock_install_process.stderr.readline = AsyncMock(return_value=b"")

        # Mock subprocess creation
        def create_subprocess_side_effect(*args, **kwargs):
            cmd = args if args else kwargs.get('args', [])
            if any('update-index' in str(arg) for arg in cmd):
                return mock_index_process
            else:
                return mock_install_process

        # Mock the final board list command
        mock_run_result = MagicMock()
        mock_run_result.returncode = 0
        mock_run_result.stdout = "ESP32 Dev Module esp32:esp32:esp32\n"

        with patch('asyncio.create_subprocess_exec', side_effect=create_subprocess_side_effect):
            with patch('asyncio.wait_for', side_effect=[
                (b"Index updated", b""),  # Index update result
                0  # Installation wait result
            ]):
                with patch('subprocess.run', return_value=mock_run_result):
                    result = await arduino_board.install_esp32(mock_context)

        print(f"📊 Installation result: {result}")

        # Verify successful installation
        assert result["success"] is True
        assert "ESP32 core installed successfully" in result["message"]
        assert "next_steps" in result
        assert isinstance(result["next_steps"], list)
        assert len(result["next_steps"]) > 0

        # Verify progress was reported
        mock_context.report_progress.assert_called()
        assert mock_context.report_progress.call_count >= 4

        # Verify context methods were called appropriately
        mock_context.info.assert_called()
        assert any("Installing ESP32 board support" in str(call)
                  for call in mock_context.info.call_args_list)

        print("✅ ESP32 installation test passed")

    @pytest.mark.asyncio
    async def test_esp32_already_installed(self, arduino_board, mock_context):
        """Test ESP32 installation when already installed"""
        print("\n🔄 Testing ESP32 already installed scenario...")

        # Mock index update (successful)
        mock_index_process = AsyncMock()
        mock_index_process.returncode = 0
        mock_index_process.communicate.return_value = (b"Index updated", b"")

        # Mock installation process (already installed)
        mock_install_process = AsyncMock()
        mock_install_process.returncode = 1  # Non-zero for already installed
        mock_install_process.wait = AsyncMock()

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

        mock_install_process.stdout = AsyncMock()
        mock_install_process.stderr = AsyncMock()
        mock_install_process.stdout.readline = AsyncMock(return_value=b"")
        mock_install_process.stderr.readline = mock_stderr_readline

        def create_subprocess_side_effect(*args, **kwargs):
            cmd = args if args else kwargs.get('args', [])
            if any('update-index' in str(arg) for arg in cmd):
                return mock_index_process
            else:
                return mock_install_process

        with patch('asyncio.create_subprocess_exec', side_effect=create_subprocess_side_effect):
            with patch('asyncio.wait_for', side_effect=[
                (b"Index updated", b""),
                1  # Installation returns 1 (already installed)
            ]):
                result = await arduino_board.install_esp32(mock_context)

        print(f"📊 Already installed result: {result}")

        # Should still be successful
        assert result["success"] is True
        assert "already installed" in result["message"].lower()

        print("✅ Already installed test passed")

    @pytest.mark.asyncio
    async def test_esp32_installation_timeout(self, arduino_board, mock_context):
        """Test ESP32 installation timeout handling"""
        print("\n⏱️ Testing ESP32 installation timeout...")

        # Mock index update (successful)
        mock_index_process = AsyncMock()
        mock_index_process.returncode = 0
        mock_index_process.communicate.return_value = (b"Index updated", b"")

        # Mock installation process that times out
        mock_install_process = AsyncMock()
        mock_install_process.wait.side_effect = asyncio.TimeoutError()
        mock_install_process.kill = AsyncMock()

        mock_install_process.stdout = AsyncMock()
        mock_install_process.stderr = AsyncMock()
        mock_install_process.stdout.readline = AsyncMock(return_value=b"Downloading...\n")
        mock_install_process.stderr.readline = AsyncMock(return_value=b"")

        def create_subprocess_side_effect(*args, **kwargs):
            cmd = args if args else kwargs.get('args', [])
            if any('update-index' in str(arg) for arg in cmd):
                return mock_index_process
            else:
                return mock_install_process

        with patch('asyncio.create_subprocess_exec', side_effect=create_subprocess_side_effect):
            with patch('asyncio.wait_for', side_effect=[
                (b"Index updated", b""),
                asyncio.TimeoutError()  # Installation times out
            ]):
                result = await arduino_board.install_esp32(mock_context)

        print(f"📊 Timeout result: {result}")

        # Should handle timeout gracefully
        assert "error" in result
        assert "timed out" in result["error"].lower()
        assert "hint" in result

        # Verify process was killed
        mock_install_process.kill.assert_called_once()

        # Verify error was reported
        mock_context.error.assert_called()

        print("✅ Timeout handling test passed")

    @pytest.mark.asyncio
    async def test_esp32_index_update_failure(self, arduino_board, mock_context):
        """Test ESP32 installation when index update fails"""
        print("\n❌ Testing index update failure...")

        # Mock index update failure
        mock_index_process = AsyncMock()
        mock_index_process.returncode = 1
        mock_index_process.communicate.return_value = (
            b"",
            b"Error updating index: connection failed"
        )

        with patch('asyncio.create_subprocess_exec', return_value=mock_index_process):
            with patch('asyncio.wait_for', return_value=(b"", b"Connection failed")):
                result = await arduino_board.install_esp32(mock_context)

        print(f"📊 Index failure result: {result}")

        # Should handle index update failure
        assert "error" in result
        assert "Failed to update board index" in result["error"]

        # Verify error was reported
        mock_context.error.assert_called()

        print("✅ Index update failure test passed")

    @pytest.mark.asyncio
    async def test_esp32_progress_tracking(self, arduino_board, mock_context):
        """Test ESP32 installation progress tracking"""
        print("\n📊 Testing progress tracking...")

        # Mock index update
        mock_index_process = AsyncMock()
        mock_index_process.returncode = 0
        mock_index_process.communicate.return_value = (b"Index updated", b"")

        # Mock installation with detailed progress
        mock_install_process = AsyncMock()
        mock_install_process.returncode = 0
        mock_install_process.wait = AsyncMock()

        progress_messages = [
            b"Downloading esp32:esp32@2.0.11 (425MB)...\n",
            b"Downloading xtensa-esp32-elf-gcc@8.4.0 (566MB)...\n",
            b"Downloading esptool_py@1.30300.0 (45MB)...\n",
            b"Installing esp32:esp32@2.0.11...\n",
            b"Installing xtensa-esp32-elf-gcc@8.4.0...\n",
            b"Installing esptool_py@1.30300.0...\n",
            b"Platform esp32:esp32@2.0.11 installed\n",
            b""  # End of stream
        ]

        message_index = 0
        async def mock_stdout_readline():
            nonlocal message_index
            if message_index < len(progress_messages):
                msg = progress_messages[message_index]
                message_index += 1
                await asyncio.sleep(0.01)  # Simulate download time
                return msg
            return b""

        mock_install_process.stdout = AsyncMock()
        mock_install_process.stderr = AsyncMock()
        mock_install_process.stdout.readline = mock_stdout_readline
        mock_install_process.stderr.readline = AsyncMock(return_value=b"")

        def create_subprocess_side_effect(*args, **kwargs):
            cmd = args if args else kwargs.get('args', [])
            if any('update-index' in str(arg) for arg in cmd):
                return mock_index_process
            else:
                return mock_install_process

        # Mock board list
        mock_run_result = MagicMock()
        mock_run_result.returncode = 0
        mock_run_result.stdout = "ESP32 boards available\n"

        with patch('asyncio.create_subprocess_exec', side_effect=create_subprocess_side_effect):
            with patch('asyncio.wait_for', side_effect=[
                (b"Index updated", b""),
                0  # Installation completes
            ]):
                with patch('subprocess.run', return_value=mock_run_result):
                    result = await arduino_board.install_esp32(mock_context)

        print(f"📊 Progress tracking result: {result}")

        # Verify successful installation
        assert result["success"] is True

        # Verify progress was tracked
        progress_calls = mock_context.report_progress.call_args_list
        assert len(progress_calls) >= 5  # Multiple progress updates

        # Verify progress values are reasonable and increasing
        progress_values = [call[0][0] for call in progress_calls]
        assert all(0 <= val <= 100 for val in progress_values)
        assert progress_values[-1] == 100  # Should end at 100%

        # Verify info messages were logged for downloads
        info_calls = mock_context.info.call_args_list
        download_messages = [call for call in info_calls
                           if any(word in str(call) for word in ["Downloading", "📦"])]
        assert len(download_messages) >= 2  # Should track multiple downloads

        print("✅ Progress tracking test passed")

    @pytest.mark.asyncio
    async def test_esp32_url_configuration(self, arduino_board, mock_context):
        """Test that ESP32 installation uses correct ESP32 board package URL"""
        print("\n🔗 Testing ESP32 URL configuration...")

        # Mock successful processes
        mock_index_process = AsyncMock()
        mock_index_process.returncode = 0
        mock_index_process.communicate.return_value = (b"Index updated", b"")

        mock_install_process = AsyncMock()
        mock_install_process.returncode = 0
        mock_install_process.wait = AsyncMock()
        mock_install_process.stdout = AsyncMock()
        mock_install_process.stderr = AsyncMock()
        mock_install_process.stdout.readline = AsyncMock(return_value=b"Platform installed\n")
        mock_install_process.stderr.readline = AsyncMock(return_value=b"")

        captured_commands = []

        def capture_subprocess_calls(*args, **kwargs):
            captured_commands.append(args)
            cmd = args if args else kwargs.get('args', [])
            if any('update-index' in str(arg) for arg in cmd):
                return mock_index_process
            else:
                return mock_install_process

        mock_run_result = MagicMock()
        mock_run_result.returncode = 0
        mock_run_result.stdout = "ESP32 boards\n"

        with patch('asyncio.create_subprocess_exec', side_effect=capture_subprocess_calls):
            with patch('asyncio.wait_for', side_effect=[
                (b"Index updated", b""),
                0
            ]):
                with patch('subprocess.run', return_value=mock_run_result):
                    result = await arduino_board.install_esp32(mock_context)

        print(f"📊 URL configuration result: {result}")

        # Verify successful installation
        assert result["success"] is True

        # Verify ESP32 URL was used
        esp32_url = "https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json"

        # Check that ESP32 URL was used in commands
        url_used = False
        for cmd_args in captured_commands:
            cmd_str = " ".join(str(arg) for arg in cmd_args)
            if "--additional-urls" in cmd_str and esp32_url in cmd_str:
                url_used = True
                break

        assert url_used, f"ESP32 URL not found in commands: {captured_commands}"

        # Verify URL was logged
        debug_calls = mock_context.debug.call_args_list
        url_logged = any(esp32_url in str(call) for call in debug_calls)
        assert url_logged, f"ESP32 URL not logged in debug messages: {debug_calls}"

        print("✅ ESP32 URL configuration test passed")


if __name__ == "__main__":
    # Run the unit tests
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
