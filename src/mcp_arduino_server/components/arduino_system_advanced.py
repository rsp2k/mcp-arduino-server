"""
Advanced Arduino System Management Component
Provides config management, bootloader operations, and sketch utilities
"""

import json
import os
import shutil
import zipfile
from typing import List, Dict, Optional, Any
from pathlib import Path
import subprocess
import logging
import yaml

from fastmcp import Context
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool
from pydantic import Field

logger = logging.getLogger(__name__)


class ArduinoSystemAdvanced(MCPMixin):
    """Advanced system management features for Arduino"""

    def __init__(self, config):
        """Initialize system manager"""
        self.config = config
        self.cli_path = config.arduino_cli_path
        self.sketch_dir = Path(config.sketch_dir).expanduser()
        self.config_file = Path.home() / ".arduino15" / "arduino-cli.yaml"

    async def _run_arduino_cli(self, args: List[str], capture_output: bool = True) -> Dict[str, Any]:
        """Run Arduino CLI command and return result"""
        cmd = [self.cli_path] + args

        try:
            if capture_output:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout
                    return {"success": False, "error": error_msg}

                # Try to parse JSON if possible
                try:
                    data = json.loads(result.stdout)
                    return {"success": True, "data": data}
                except json.JSONDecodeError:
                    return {"success": True, "output": result.stdout}
            else:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return {"success": True, "process": process}

        except Exception as e:
            logger.error(f"Arduino CLI error: {e}")
            return {"success": False, "error": str(e)}

    @mcp_tool(
        name="arduino_config_init",
        description="Initialize Arduino CLI configuration"
    )
    async def config_init(
        self,
        overwrite: bool = Field(False, description="Overwrite existing configuration"),
        additional_urls: Optional[List[str]] = Field(None, description="Additional board package URLs"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Initialize Arduino CLI configuration with defaults"""
        args = ["config", "init"]

        if overwrite or not self.config_file.exists():
            args.append("--overwrite")

        result = await self._run_arduino_cli(args)

        if result["success"] and additional_urls:
            # Add additional board URLs
            for url in additional_urls:
                await self.config_set(
                    key="board_manager.additional_urls",
                    value=additional_urls,
                    ctx=ctx
                )

        if result["success"]:
            return {
                "success": True,
                "config_file": str(self.config_file),
                "message": "Configuration initialized successfully"
            }

        return result

    @mcp_tool(
        name="arduino_config_get",
        description="Get Arduino CLI configuration value"
    )
    async def config_get(
        self,
        key: str = Field(..., description="Configuration key (e.g., 'board_manager.additional_urls')"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Get a specific configuration value"""
        args = ["config", "get", key]

        result = await self._run_arduino_cli(args)

        if result["success"]:
            value = result.get("output", "").strip()

            # Parse JSON arrays if present
            if value.startswith("[") and value.endswith("]"):
                try:
                    value = json.loads(value)
                except:
                    pass

            return {
                "success": True,
                "key": key,
                "value": value
            }

        return result

    @mcp_tool(
        name="arduino_config_set",
        description="Set Arduino CLI configuration value"
    )
    async def config_set(
        self,
        key: str = Field(..., description="Configuration key"),
        value: Any = Field(..., description="Configuration value"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Set a configuration value"""
        # Convert value to appropriate format
        if isinstance(value, list):
            # For arrays, set each item
            for item in value:
                args = ["config", "add", key, str(item)]
                result = await self._run_arduino_cli(args)
                if not result["success"]:
                    return result
        else:
            args = ["config", "set", key, str(value)]
            result = await self._run_arduino_cli(args)

        if result["success"]:
            return {
                "success": True,
                "key": key,
                "value": value,
                "message": f"Configuration '{key}' updated"
            }

        return result

    @mcp_tool(
        name="arduino_config_dump",
        description="Dump entire Arduino CLI configuration"
    )
    async def config_dump(
        self,
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Get the complete Arduino CLI configuration"""
        args = ["config", "dump", "--json"]

        result = await self._run_arduino_cli(args)

        if result["success"]:
            config = result.get("data", {})

            # Organize configuration sections
            organized = {
                "board_manager": config.get("board_manager", {}),
                "daemon": config.get("daemon", {}),
                "directories": config.get("directories", {}),
                "library": config.get("library", {}),
                "logging": config.get("logging", {}),
                "metrics": config.get("metrics", {}),
                "output": config.get("output", {}),
                "sketch": config.get("sketch", {}),
                "updater": config.get("updater", {})
            }

            return {
                "success": True,
                "config_file": str(self.config_file),
                "configuration": organized,
                "raw_config": config
            }

        return result

    @mcp_tool(
        name="arduino_burn_bootloader",
        description="Burn bootloader to a board using a programmer"
    )
    async def burn_bootloader(
        self,
        fqbn: str = Field(..., description="Board FQBN"),
        port: str = Field(..., description="Port where board is connected"),
        programmer: str = Field(..., description="Programmer to use (e.g., 'usbasp', 'stk500v1')"),
        verify: bool = Field(True, description="Verify after burning"),
        verbose: bool = Field(False, description="Verbose output"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """
        Burn bootloader to a board

        This is typically used for:
        - New ATmega chips without bootloader
        - Recovering bricked boards
        - Changing bootloader versions
        """
        args = ["burn-bootloader",
                "--fqbn", fqbn,
                "--port", port,
                "--programmer", programmer]

        if verify:
            args.append("--verify")

        if verbose:
            args.append("--verbose")

        result = await self._run_arduino_cli(args)

        if result["success"]:
            return {
                "success": True,
                "board": fqbn,
                "port": port,
                "programmer": programmer,
                "message": "Bootloader burned successfully"
            }

        return result

    @mcp_tool(
        name="arduino_sketch_archive",
        description="Create an archive of a sketch for sharing"
    )
    async def archive_sketch(
        self,
        sketch_name: str = Field(..., description="Name of the sketch to archive"),
        output_path: Optional[str] = Field(None, description="Output path for archive"),
        include_libraries: bool = Field(False, description="Include used libraries"),
        include_build_artifacts: bool = Field(False, description="Include compiled binaries"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Create a ZIP archive of a sketch for easy sharing"""
        sketch_path = self.sketch_dir / sketch_name

        if not sketch_path.exists():
            return {"success": False, "error": f"Sketch '{sketch_name}' not found"}

        # Default output path
        if not output_path:
            output_path = str(self.sketch_dir / f"{sketch_name}.zip")

        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add sketch files
                for file in sketch_path.rglob("*"):
                    if file.is_file():
                        # Skip build artifacts unless requested
                        if "/build/" in str(file) and not include_build_artifacts:
                            continue

                        arcname = file.relative_to(sketch_path.parent)
                        zipf.write(file, arcname)

                # Add metadata
                metadata = {
                    "sketch_name": sketch_name,
                    "created_at": os.path.getmtime(sketch_path),
                    "arduino_cli_version": self._get_cli_version()
                }

                # Check for attached board
                sketch_json = sketch_path / "sketch.json"
                if sketch_json.exists():
                    with open(sketch_json) as f:
                        sketch_data = json.load(f)
                        metadata["board"] = sketch_data.get("cpu", {}).get("fqbn")

                # Write metadata
                zipf.writestr(f"{sketch_name}/metadata.json", json.dumps(metadata, indent=2))

            # Get archive info
            archive_size = Path(output_path).stat().st_size

            return {
                "success": True,
                "sketch": sketch_name,
                "archive": output_path,
                "size_bytes": archive_size,
                "size_mb": archive_size / (1024 * 1024),
                "included_libraries": include_libraries,
                "included_build": include_build_artifacts
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to create archive: {str(e)}"}

    @mcp_tool(
        name="arduino_sketch_new",
        description="Create new sketch from template"
    )
    async def create_sketch_from_template(
        self,
        sketch_name: str = Field(..., description="Name for the new sketch"),
        template: str = Field("default", description="Template type: default, blink, serial, wifi, sensor"),
        board: Optional[str] = Field(None, description="Board FQBN to attach"),
        metadata: Optional[Dict[str, str]] = Field(None, description="Sketch metadata"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Create a new sketch from predefined templates"""

        sketch_path = self.sketch_dir / sketch_name

        if sketch_path.exists():
            return {"success": False, "error": f"Sketch '{sketch_name}' already exists"}

        # Create sketch directory
        sketch_path.mkdir(parents=True)
        sketch_file = sketch_path / f"{sketch_name}.ino"

        # Templates
        templates = {
            "default": """void setup() {
  // Put your setup code here, to run once:

}

void loop() {
  // Put your main code here, to run repeatedly:

}
""",
            "blink": """// LED Blink Example
const int LED = LED_BUILTIN;

void setup() {
  pinMode(LED, OUTPUT);
}

void loop() {
  digitalWrite(LED, HIGH);
  delay(1000);
  digitalWrite(LED, LOW);
  delay(1000);
}
""",
            "serial": """// Serial Communication Example
void setup() {
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for serial port to connect (needed for native USB)
  }
  Serial.println("Serial communication started!");
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    Serial.print("Received: ");
    Serial.println(c);
  }
  delay(100);
}
""",
            "wifi": """// WiFi Connection Example (ESP32/ESP8266)
#ifdef ESP32
  #include <WiFi.h>
#else
  #include <ESP8266WiFi.h>
#endif

const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";

void setup() {
  Serial.begin(115200);
  delay(10);

  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // Your code here
  delay(1000);
}
""",
            "sensor": """// Sensor Reading Example
const int SENSOR_PIN = A0;
const int LED_PIN = LED_BUILTIN;

int sensorValue = 0;
int threshold = 512;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(SENSOR_PIN, INPUT);

  Serial.println("Sensor monitoring started");
}

void loop() {
  sensorValue = analogRead(SENSOR_PIN);

  Serial.print("Sensor value: ");
  Serial.println(sensorValue);

  // Turn LED on if threshold exceeded
  if (sensorValue > threshold) {
    digitalWrite(LED_PIN, HIGH);
  } else {
    digitalWrite(LED_PIN, LOW);
  }

  delay(100);
}
"""
        }

        # Write template
        template_code = templates.get(template, templates["default"])
        sketch_file.write_text(template_code)

        # Create metadata file if requested
        if metadata or board:
            sketch_json = sketch_path / "sketch.json"
            json_data = {}

            if board:
                json_data["cpu"] = {"fqbn": board}

            if metadata:
                json_data["metadata"] = metadata

            with open(sketch_json, 'w') as f:
                json.dump(json_data, f, indent=2)

        return {
            "success": True,
            "sketch": sketch_name,
            "path": str(sketch_path),
            "template": template,
            "board_attached": board is not None,
            "message": f"Sketch '{sketch_name}' created from '{template}' template"
        }

    def _get_cli_version(self) -> str:
        """Get Arduino CLI version"""
        try:
            result = subprocess.run(
                [self.cli_path, "version"],
                capture_output=True,
                text=True
            )
            return result.stdout.strip()
        except:
            return "unknown"

    @mcp_tool(
        name="arduino_monitor_advanced",
        description="Use Arduino CLI's built-in serial monitor with advanced features"
    )
    async def monitor_advanced(
        self,
        port: str = Field(..., description="Serial port to monitor"),
        baudrate: int = Field(115200, description="Baud rate"),
        config: Optional[Dict[str, Any]] = Field(None, description="Monitor configuration"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """
        Start Arduino CLI's built-in monitor with advanced features

        Config options:
        - timestamp: Add timestamps to output
        - echo: Echo sent characters
        - eol: End of line (cr, lf, crlf)
        - filter: Regex filter for output
        - raw: Raw output mode
        """
        args = ["monitor", "--port", port, "--config", f"baudrate={baudrate}"]

        if config:
            for key, value in config.items():
                args.extend(["--config", f"{key}={value}"])

        # This will need to run in background or streaming mode
        result = await self._run_arduino_cli(args, capture_output=False)

        if result["success"]:
            return {
                "success": True,
                "port": port,
                "baudrate": baudrate,
                "config": config or {},
                "message": "Monitor started",
                "process": result.get("process")
            }

        return result