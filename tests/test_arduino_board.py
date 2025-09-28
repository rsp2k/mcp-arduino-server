"""
Tests for ArduinoBoard component
"""
import json
import subprocess
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tests.conftest import assert_logged_info, assert_progress_reported


class TestArduinoBoard:
    """Test suite for ArduinoBoard component"""

    @pytest.mark.asyncio
    async def test_list_boards_found(self, board_component, test_context, mock_arduino_cli):
        """Test listing connected boards with successful detection"""
        mock_response = {
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
                    ],
                    "hardware_id": "USB\\VID_2341&PID_0043"
                },
                {
                    "port": {
                        "address": "/dev/ttyACM0",
                        "protocol": "serial",
                        "label": "Arduino Nano"
                    },
                    "matching_boards": [
                        {
                            "name": "Arduino Nano",
                            "fqbn": "arduino:avr:nano"
                        }
                    ]
                }
            ]
        }
        mock_arduino_cli.return_value.stdout = json.dumps(mock_response)
        mock_arduino_cli.return_value.returncode = 0

        result = await board_component.list_boards(test_context)

        assert "Found 2 connected board(s)" in result
        assert "/dev/ttyUSB0" in result
        assert "/dev/ttyACM0" in result
        assert "Arduino Uno" in result
        assert "arduino:avr:uno" in result

        # Verify arduino-cli was called correctly
        mock_arduino_cli.assert_called_once()
        call_args = mock_arduino_cli.call_args[0][0]
        assert "board" in call_args
        assert "list" in call_args
        assert "--format" in call_args
        assert "json" in call_args

    @pytest.mark.asyncio
    async def test_list_boards_empty(self, board_component, test_context, mock_arduino_cli):
        """Test listing boards when none are connected"""
        mock_arduino_cli.return_value.stdout = '{"detected_ports": []}'
        mock_arduino_cli.return_value.returncode = 0

        result = await board_component.list_boards(test_context)

        assert "No Arduino boards detected" in result
        assert "troubleshooting steps" in result
        assert "USB cable connection" in result

    @pytest.mark.asyncio
    async def test_list_boards_no_matching(self, board_component, test_context, mock_arduino_cli):
        """Test listing boards with detected ports but no matching board"""
        mock_response = {
            "detected_ports": [
                {
                    "port": {
                        "address": "/dev/ttyUSB0",
                        "protocol": "serial",
                        "label": "Unknown Device"
                    },
                    "matching_boards": []
                }
            ]
        }
        mock_arduino_cli.return_value.stdout = json.dumps(mock_response)
        mock_arduino_cli.return_value.returncode = 0

        result = await board_component.list_boards(test_context)

        assert "/dev/ttyUSB0" in result
        assert "No matching board found" in result
        assert "install core" in result

    @pytest.mark.asyncio
    async def test_search_boards_success(self, board_component, test_context, mock_arduino_cli):
        """Test successful board search"""
        mock_response = {
            "boards": [
                {
                    "name": "Arduino Uno",
                    "fqbn": "arduino:avr:uno",
                    "platform": {
                        "id": "arduino:avr",
                        "maintainer": "Arduino"
                    }
                },
                {
                    "name": "Arduino Nano",
                    "fqbn": "arduino:avr:nano",
                    "platform": {
                        "id": "arduino:avr",
                        "maintainer": "Arduino"
                    }
                }
            ]
        }
        mock_arduino_cli.return_value.stdout = json.dumps(mock_response)
        mock_arduino_cli.return_value.returncode = 0

        result = await board_component.search_boards(
            test_context,
            "uno"
        )

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["boards"]) == 2
        assert result["boards"][0]["name"] == "Arduino Uno"
        assert result["boards"][0]["fqbn"] == "arduino:avr:uno"

    @pytest.mark.asyncio
    async def test_search_boards_empty(self, board_component, test_context, mock_arduino_cli):
        """Test board search with no results"""
        mock_arduino_cli.return_value.stdout = '{"boards": []}'
        mock_arduino_cli.return_value.returncode = 0

        result = await board_component.search_boards(
            test_context,
            "nonexistent"
        )

        assert result["count"] == 0
        assert result["boards"] == []
        assert "No board definitions found" in result["message"]

    @pytest.mark.asyncio
    async def test_install_core_success(self, board_component, test_context, mock_async_subprocess):
        """Test successful core installation with progress"""
        mock_process = mock_async_subprocess.return_value
        mock_process.returncode = 0

        # Simulate progress output
        mock_process.stdout.readline = AsyncMock(side_effect=[
            b'Downloading arduino:avr@1.8.5...\n',
            b'Installing arduino:avr@1.8.5...\n',
            b'Platform arduino:avr@1.8.5 installed\n',
            b''
        ])
        mock_process.stderr.readline = AsyncMock(return_value=b'')
        mock_process.wait = AsyncMock(return_value=0)

        result = await board_component.install_core(
            test_context,
            "arduino:avr"
        )

        assert result["success"] is True
        assert "installed successfully" in result["message"]

        # Verify progress was reported
        assert_progress_reported(test_context, min_calls=2)
        assert_logged_info(test_context, "Starting installation")

    @pytest.mark.asyncio
    async def test_install_core_already_installed(self, board_component, test_context, mock_async_subprocess):
        """Test installing core that's already installed"""
        mock_process = mock_async_subprocess.return_value
        mock_process.returncode = 1

        # Simulate stderr for already installed
        mock_process.stderr.readline = AsyncMock(side_effect=[
            b'Platform arduino:avr already installed\n',
            b''
        ])
        mock_process.stdout.readline = AsyncMock(return_value=b'')
        mock_process.wait = AsyncMock(return_value=1)

        result = await board_component.install_core(
            test_context,
            "arduino:avr"
        )

        assert result["success"] is True
        assert "already installed" in result["message"]

    @pytest.mark.asyncio
    async def test_install_core_failure(self, board_component, test_context, mock_async_subprocess):
        """Test core installation failure"""
        mock_process = mock_async_subprocess.return_value
        mock_process.returncode = 1

        mock_process.stderr.readline = AsyncMock(side_effect=[
            b'Error: invalid platform specification\n',
            b''
        ])
        mock_process.stdout.readline = AsyncMock(return_value=b'')
        mock_process.wait = AsyncMock(return_value=1)

        result = await board_component.install_core(
            test_context,
            "invalid:core"
        )

        assert "error" in result
        assert "installation failed" in result["error"]
        assert "invalid platform" in result["stderr"]

    @pytest.mark.asyncio
    async def test_list_cores_success(self, board_component, test_context, mock_arduino_cli):
        """Test listing installed cores"""
        mock_response = {
            "platforms": [
                {
                    "id": "arduino:avr",
                    "installed": "1.8.5",
                    "latest": "1.8.6",
                    "name": "Arduino AVR Boards",
                    "maintainer": "Arduino",
                    "website": "http://www.arduino.cc/",
                    "boards": [
                        {"name": "Arduino Uno"},
                        {"name": "Arduino Nano"}
                    ]
                },
                {
                    "id": "esp32:esp32",
                    "installed": "2.0.9",
                    "latest": "2.0.11",
                    "name": "ESP32 Arduino",
                    "maintainer": "Espressif Systems"
                }
            ]
        }
        mock_arduino_cli.return_value.stdout = json.dumps(mock_response)
        mock_arduino_cli.return_value.returncode = 0

        result = await board_component.list_cores(test_context)

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["cores"]) == 2
        assert result["cores"][0]["id"] == "arduino:avr"
        assert result["cores"][0]["installed"] == "1.8.5"
        assert len(result["cores"][0]["boards"]) == 2

    @pytest.mark.asyncio
    async def test_list_cores_empty(self, board_component, test_context, mock_arduino_cli):
        """Test listing cores when none are installed"""
        mock_arduino_cli.return_value.stdout = '{"platforms": []}'
        mock_arduino_cli.return_value.returncode = 0

        result = await board_component.list_cores(test_context)

        assert result["count"] == 0
        assert result["cores"] == []
        assert "No cores installed" in result["message"]
        assert "arduino_install_core" in result["hint"]

    @pytest.mark.asyncio
    async def test_update_cores_success(self, board_component, test_context, mock_arduino_cli):
        """Test successful core update"""
        # Mock two calls: update-index and upgrade
        mock_arduino_cli.side_effect = [
            # First call: core update-index
            Mock(returncode=0, stdout="Updated package index"),
            # Second call: core upgrade
            Mock(returncode=0, stdout="All platforms upgraded")
        ]

        result = await board_component.update_cores(test_context)

        assert result["success"] is True
        assert "updated successfully" in result["message"]

        # Verify both commands were called
        assert mock_arduino_cli.call_count == 2

        # Check first call (update-index)
        first_call = mock_arduino_cli.call_args_list[0][0][0]
        assert "core" in first_call
        assert "update-index" in first_call

        # Check second call (upgrade)
        second_call = mock_arduino_cli.call_args_list[1][0][0]
        assert "core" in second_call
        assert "upgrade" in second_call

    @pytest.mark.asyncio
    async def test_update_cores_already_updated(self, board_component, test_context, mock_arduino_cli):
        """Test core update when already up to date"""
        mock_arduino_cli.side_effect = [
            # First call: update-index
            Mock(returncode=0, stdout="Updated package index"),
            # Second call: upgrade (already up to date)
            Mock(returncode=1, stderr="All platforms are already up to date")
        ]

        result = await board_component.update_cores(test_context)

        assert result["success"] is True
        assert "already up to date" in result["message"]

    @pytest.mark.asyncio
    async def test_update_cores_index_failure(self, board_component, test_context, mock_arduino_cli):
        """Test core update with index update failure"""
        mock_arduino_cli.return_value.returncode = 1
        mock_arduino_cli.return_value.stderr = "Network error"

        result = await board_component.update_cores(test_context)

        assert "error" in result
        assert "Failed to update core index" in result["error"]
        assert "Network error" in result["stderr"]

    @pytest.mark.asyncio
    async def test_list_connected_boards_resource(self, board_component):
        """Test the MCP resource for listing boards"""
        with patch.object(board_component, 'list_boards') as mock_list:
            mock_list.return_value = "Found 1 connected board(s):\n\n🔌 Port: /dev/ttyUSB0"

            result = await board_component.list_connected_boards()

            assert "Found 1 connected board" in result
            mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_board_operations_timeout(self, board_component, test_context, mock_arduino_cli):
        """Test timeout handling in board operations"""
        # Mock timeout for list_boards
        mock_arduino_cli.side_effect = subprocess.TimeoutExpired("arduino-cli", 30)

        result = await board_component.list_boards(test_context)

        assert "timed out" in result

    @pytest.mark.asyncio
    async def test_board_operations_json_parse_error(self, board_component, test_context, mock_arduino_cli):
        """Test JSON parsing error handling"""
        mock_arduino_cli.return_value.returncode = 0
        mock_arduino_cli.return_value.stdout = "invalid json"

        result = await board_component.list_boards(test_context)

        assert "Failed to parse board list" in result

    @pytest.mark.asyncio
    async def test_search_boards_error(self, board_component, test_context, mock_arduino_cli):
        """Test board search command error"""
        mock_arduino_cli.return_value.returncode = 1
        mock_arduino_cli.return_value.stderr = "Invalid search term"

        result = await board_component.search_boards(test_context, "")

        assert "error" in result
        assert "Board search failed" in result["error"]
        assert "Invalid search term" in result["stderr"]
