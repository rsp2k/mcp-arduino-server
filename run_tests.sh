#!/bin/bash
# Run tests for mcp-arduino-server

echo "🧪 Running mcp-arduino-server tests..."
echo "=================================="

# Set PYTHONPATH to include src directory
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}src"

# Run tests with coverage if available
if command -v coverage &> /dev/null; then
    echo "📊 Running with coverage..."
    coverage run -m pytest tests/ -v
    echo ""
    echo "📈 Coverage Report:"
    coverage report -m --include="src/*"
    coverage html
    echo "📁 HTML coverage report generated in htmlcov/"
else
    echo "🚀 Running tests..."
    python -m pytest tests/ -v
fi

# Run specific test suites if argument provided
if [ "$1" != "" ]; then
    echo ""
    echo "🎯 Running specific test: $1"
    python -m pytest "tests/$1" -v
fi

echo ""
echo "✅ Test run complete!"