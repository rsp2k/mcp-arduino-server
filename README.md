# MCP Arduino Server (mcp-arduino-server)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) <!-- Assuming MIT based on pyproject.toml -->
<!-- Add other badges like PyPI version if applicable -->

MCP Server for Arduino CLI providing sketch, board, library, and file management tools. Powered by FastMCP.

## Overview

This server acts as a bridge between the Model Context Protocol (MCP) and the `arduino-cli`, allowing AI agents or other MCP clients to interact with Arduino development workflows. It provides tools for managing sketches, compiling code, uploading to boards, managing libraries, discovering hardware, and performing basic file operations within a restricted environment.

## Features

*   **Sketch Management**: Create, list, read, and write Arduino sketches (`.ino`, `.h` files).
    *   Writing the main `.ino` file automatically triggers compilation for validation.
    *   **Auto-Open**: Newly created `.ino` files are automatically opened in your default editor.
*   **WireViz Circuit Diagrams**:
    *   **YAML Authoring Help:** Use the built-in `getWirevizInstructions` tool to fetch comprehensive guidelines and an example for creating valid WireViz YAML. The instructions cover how to define connectors (components), cables, connections, and required metadata, along with a checklist and color code reference.
    *   **Diagram Generation:** Use the `generate_diagram_from_yaml` tool to generate a circuit diagram PNG from your YAML. You can specify a sketch directory for output, or let the tool create a timestamped folder. The PNG is returned as base64 and opened automatically in your image viewer.
    *   **Typical Workflow:**
        1. Call `getWirevizInstructions` to see the YAML structure and example.
        2. Author your YAML to describe your Arduino circuit.
        3. Call `generate_diagram_from_yaml` with your YAML to get a ready-to-use PNG wiring diagram.
    *   **Error Handling:** The server validates YAML structure, manages output files, and provides clear error messages for invalid YAML, missing dependencies, or WireViz failures.
    *   **Example YAML:** (see the output of `getWirevizInstructions` for a full template)

        ```yaml
        connectors:
          Arduino Uno:
            pinlabels: ["5V", "GND", "D2", "D3", "A4", "A5"]
            notes: Main control board
          SSD1306 OLED Display:
            pinlabels: ["VCC", "GND", "SCL", "SDA"]
            notes: Display module
          # ... more components ...
        cables:
          W_SSD1306_OLED:
            colors: [RD, BK, TQ, VT]
            category: bundle
        connections:
          - # Example connection
            - Arduino Uno: [3]
            - W_SSD1306_OLED: [1]
            - SSD1306 OLED Display: [1]
        metadata:
          description: "Wiring diagram for Arduino Uno with SSD1306 OLED Display and Push Buttons"
          author: "User"
          date: "2024-06-23"
        ```

*   **Code Verification**: Compile sketches using `verify_code` without uploading.
*   **Uploading**: Compile and upload sketches to connected boards.
*   **Library Management**:
    *   Search the online Arduino Library Manager index.
    *   Search local platform libraries (fuzzy search if `thefuzz` is installed).
    *   Install libraries from the index.
    *   List examples from installed libraries.
*   **Board Management**:
    *   Discover connected boards and their details (Port, Name, FQBN).
    *   List platform libraries associated with connected boards.
    *   Search the online board index for FQBNs.
*   **File Operations**: Basic, restricted file reading, writing, renaming, and removal within the user's home directory or designated sketch directories.
    *   **Security**: Operations are sandboxed primarily to `~/Documents/Arduino_MCP_Sketches/` and the user's home directory (`~`) with strong warnings for destructive actions.
*   **Robust Error Handling & Logging**: Extensive logging, improved error messages, and strict path validation for all file operations. Security is emphasized throughout.

## Prerequisites

*   **Python**: **3.8+** (3.10+ recommended; required by dependencies like `mcp[cli]`)
*   **arduino-cli**: Must be installed and accessible in the system `PATH` or common locations (e.g., `/usr/local/bin`, `/opt/homebrew/bin`). The server attempts auto-detection.
*   **WireViz**: Required for circuit diagram generation. Install and ensure it's in your PATH.
*   **MCP SDK**: Installed via the project dependencies (`mcp[cli]`).
*   **Fuzzy Search (Optional but Recommended)**: Installed via project dependencies (`thefuzz[speedup]>=0.20.0`). Enables fuzzy matching for local library search.

## Installation

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <your-repo-url> # Replace <your-repo-url> with the actual URL
    cd mcp-arduino-server
    ```
2.  **Set up Python 3.10+:** Ensure you have a Python version of 3.10 or newer installed and active. Using `pyenv` is recommended:
    ```bash
    # Example using pyenv
    pyenv install 3.11.6 # Or latest 3.10+
    pyenv local 3.11.6  # Set for this project directory
    ```
3.  **Install dependencies using `uv` (Recommended) or `pip`:**

    *   **Using `uv`:**
        ```bash
        # Install uv if you haven't already (see uv documentation)
        # Create a virtual environment
        uv venv
        # Install the project and dependencies
        uv pip install .
        ```
    *   **Using `pip`:**
        ```bash
        # Create a virtual environment (optional but recommended)
        python -m venv .venv
        source .venv/bin/activate # Linux/macOS
        # .\.venv\Scripts\activate # Windows

        # Install the project and dependencies
        pip install .

        # Or, if not cloning, install dependencies directly (less common):
        # pip install "mcp[cli]" "thefuzz[speedup]>=0.20.0"
        ```
4.  **Ensure `arduino-cli` is installed and configured:**
    *   Follow the official [arduino-cli installation guide](https://arduino.github.io/arduino-cli/latest/installation/).
    *   You might need to install board cores (e.g., `arduino-cli core install arduino:avr`).

## Configuration

The server uses the following default paths and settings. Some can be overridden via environment variables.

*   **Sketches Base Directory**: `~/Documents/Arduino_MCP_Sketches/`
*   **Build Temp Directory**: `~/Documents/Arduino_MCP_Sketches/_build_temp/`
*   **Arduino Data Directory**: Auto-detected (`~/.arduino15` or `~/Library/Arduino15`)
*   **Arduino User Directory**: `~/Documents/Arduino/`
*   **Arduino CLI Path**: Auto-detected via `shutil.which` and common paths. Override with `ARDUINO_CLI_PATH` environment variable.
*   **WireViz Path**: Auto-detected via `shutil.which` (expects `wireviz` command). Override with `WIREVIZ_PATH` environment variable.
*   **Default FQBN (for auto-compile on write)**: `arduino:avr:uno`. Override via the `board_fqbn` argument in `write_file`.
*   **Log Level**: Controlled by the `LOG_LEVEL` environment variable (e.g., `DEBUG`, `INFO`, `WARNING`). Defaults to `INFO`.

## Usage

Run the server using the installed command-line script within its environment:

*   **Using `uv`:**
    ```bash
    uv run mcp-arduino-server
    ```
*   **Using `pip` (with activated venv):**
    ```bash
    # Ensure your virtual environment is activated (source .venv/bin/activate)
    mcp-arduino-server
    ```

### Using WireViz Tools

- **YAML Authoring Help:** Call `getWirevizInstructions()` to receive comprehensive guidelines, a checklist, and a ready-to-use example for authoring valid WireViz YAML for Arduino diagrams.
- **Diagram Generation:** Call `generate_diagram_from_yaml(yaml_content: str, sketch_name: str = "", output_filename_base: str = "circuit")` to generate a PNG wiring diagram from your YAML. The tool validates your YAML, manages output files, returns a confirmation and the PNG image (base64), and opens it automatically in your image viewer.
- **Workflow:**
    1. Use `getWirevizInstructions` to learn the YAML format.
    2. Write your YAML describing your circuit.
    3. Use `generate_diagram_from_yaml` to create and view your diagram.

### Auto-Open Feature

- When you create a new sketch or generate a diagram, the relevant file will open automatically in your system's default application (editor or image viewer).

### Error Handling

- All file operations and CLI interactions include robust error messages and logging. Check logs for troubleshooting details.

The server will start and listen for connections from an MCP client via standard input/output (`stdio`).

## Available Tools (MCP Interface)

The following tools are exposed via the MCP interface:

*   `create_new_sketch(sketch_name: str)`: Creates a new sketch directory and `.ino` file.
*   `list_sketches()`: Lists valid sketches in the sketches directory.
*   `read_file(filepath: str)`: Reads a file; concatenates all `.ino`/`.h` files if reading the main sketch `.ino`.
*   `write_file(filepath: str, content: str, board_fqbn: str = DEFAULT_FQBN)`: Writes content to a file; restricted paths; auto-compiles main `.ino` files.
*   `rename_file(old_path: str, new_path: str)`: Renames/moves a file/directory within the home directory.
*   `remove_file(filepath: str)`: Removes a file (not directories) within the home directory. **Irreversible.**
*   `list_boards()`: Lists connected boards, their FQBNs, and platform libraries.
*   `board_search(board_name_query: str)`: Searches the online index for board FQBNs.
*   `verify_code(sketch_name: str, board_fqbn: str)`: Compiles a sketch without uploading.
*   `upload_sketch(sketch_name: str, port: str, board_fqbn: str)`: Compiles and uploads a sketch.
*   `lib_search(library_name: str, limit: int = 15)`: Searches online and local platform libraries.
*   `lib_install(library_name: str)`: Installs/updates a library from the index.
*   `list_library_examples(library_name: str)`: Lists examples for an installed library.
*   `getWirevizInstructions()`: Returns detailed YAML authoring instructions and a template for WireViz diagrams.
*   `generate_diagram_from_yaml(yaml_content: str, sketch_name: str = "", output_filename_base: str = "circuit")`: Generates a PNG wiring diagram from YAML, returns image and confirmation, opens PNG automatically.

Refer to the server script's docstrings (`src/mcp_arduino_server/server.py`) for detailed arguments, return values, and potential errors for each tool.

## Debugging Tips

*   **Check Server Logs**: Detailed errors from `arduino-cli` are logged by the server. Increase verbosity with `export LOG_LEVEL=DEBUG`.
*   **Permissions**: Ensure the user running the server has write access to sketch/build directories and read/write access to serial ports (e.g., add user to `dialout` group on Linux).
*   **Environment PATH**: Verify `arduino-cli` and necessary toolchains (e.g., `avr-gcc`, `bossac`) are in the `PATH` accessible to the server process.
*   **Cores/Toolchains**: Use `arduino-cli core install <core_spec>` (e.g., `arduino:avr`) if compilation fails due to missing cores.
*   **`arduino-cli` Commands**: Test `arduino-cli` commands directly in your terminal to isolate issues.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details (assuming MIT license).
