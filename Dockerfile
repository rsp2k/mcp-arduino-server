# Use official uv image with Python 3.11
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Arduino CLI
ARG ARDUINO_CLI_VERSION=latest
RUN curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | \
    sh -s ${ARDUINO_CLI_VERSION} && \
    mv bin/arduino-cli /usr/local/bin/ && \
    rm -rf bin

# Copy dependency files with bind mounts to avoid cache invalidation
COPY pyproject.toml .
COPY README.md .
COPY LICENSE .

# Install dependencies with cache mount for uv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --compile-bytecode \
    --no-deps -e .

# Copy source code
COPY src/ src/

# Install the package
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_COMPILE_BYTECODE=1 uv pip install --system --no-editable .

# Production stage
FROM python:3.11-slim-bookworm AS production

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r mcp && useradd -r -g mcp -m -d /home/mcp mcp

# Copy Arduino CLI from builder
COPY --from=builder /usr/local/bin/arduino-cli /usr/local/bin/arduino-cli

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Set up working directory
WORKDIR /home/mcp
USER mcp

# Create necessary directories
RUN mkdir -p ~/Documents/Arduino_MCP_Sketches/_build_temp \
    && mkdir -p ~/.arduino15 \
    && mkdir -p ~/Documents/Arduino/libraries

# Initialize Arduino CLI
RUN arduino-cli config init

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    MCP_SKETCH_DIR=/home/mcp/Documents/Arduino_MCP_Sketches/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import mcp_arduino_server; print('OK')" || exit 1

# Default command
CMD ["mcp-arduino-server"]

# Development stage
FROM ghcr.io/astral-sh/uv:python3.11-bookworm AS development

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Install Arduino CLI
ARG ARDUINO_CLI_VERSION=latest
RUN curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | \
    sh -s ${ARDUINO_CLI_VERSION} && \
    mv bin/arduino-cli /usr/local/bin/ && \
    rm -rf bin

WORKDIR /app

# Copy dependency files
COPY pyproject.toml .
COPY README.md .
COPY LICENSE .

# Install all dependencies including dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -e ".[dev]"

# Set environment for development
ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=DEBUG \
    UV_COMPILE_BYTECODE=0 \
    MCP_SKETCH_DIR=/app/sketches/

# Create sketch directory
RUN mkdir -p /app/sketches/_build_temp

# Development command with hot-reload using watchmedo
CMD ["watchmedo", "auto-restart", "--recursive", \
     "--pattern=*.py", "--directory=/app/src", \
     "python", "-m", "mcp_arduino_server.server"]