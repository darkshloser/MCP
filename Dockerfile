# Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy source code
COPY src/ src/
COPY config/ config/

# Create logs directory
RUN mkdir -p logs

# Set Python path
ENV PYTHONPATH=/app/src
ENV MCP_CONFIG_PATH=/app/config/settings.yaml

# Default command
CMD ["python", "-m", "mcp_server.main"]
