#!/bin/bash
# MCP Arduino Server Installation Script

set -e

echo "🚀 MCP Arduino Server Installation"
echo "=================================="

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install it first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check for arduino-cli
if ! command -v arduino-cli &> /dev/null; then
    echo "⚠️  arduino-cli is not installed. Installing..."
    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
    sudo mv bin/arduino-cli /usr/local/bin/
    rm -rf bin
    echo "✅ arduino-cli installed"
else
    echo "✅ arduino-cli found"
fi

# Install the package
echo ""
echo "📦 Installing MCP Arduino Server..."
uv pip install -e ".[dev]"

# Create necessary directories
echo ""
echo "📁 Creating directories..."
mkdir -p ~/Documents/Arduino_MCP_Sketches/_build_temp
mkdir -p ~/.arduino15
mkdir -p ~/Documents/Arduino/libraries

# Initialize Arduino CLI
echo ""
echo "🔧 Initializing Arduino CLI..."
arduino-cli config init || true

# Install common Arduino cores
echo ""
echo "📥 Installing Arduino AVR core..."
arduino-cli core install arduino:avr || true

echo ""
echo "✅ Installation complete!"
echo ""
echo "To use with Claude Code:"
echo "  1. Set your OpenAI API key:"
echo "     export OPENAI_API_KEY='your-key-here'"
echo ""
echo "  2. Add to Claude Code configuration:"
echo '     claude mcp add arduino "uvx mcp-arduino-server"'
echo ""
echo "Or run directly:"
echo "  uvx mcp-arduino-server"