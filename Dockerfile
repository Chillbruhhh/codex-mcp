# Codex CLI MCP Server Dockerfile
FROM python:3.12-slim

# Install system dependencies including Docker CLI
RUN apt-get update && apt-get install -y \
    curl \
    git \
    nodejs \
    npm \
    ca-certificates \
    gnupg \
    lsb-release \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Create codex user for running containers
RUN groupadd -r codex && useradd -r -g codex -s /bin/bash -m codex

# Install Codex CLI globally
RUN npm install -g @openai/codex

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY server.py .
COPY entrypoint.sh .

# Ensure proper line endings and permissions for entrypoint and scripts
RUN chmod +x entrypoint.sh && \
    chmod +x scripts/*.sh && \
    # Convert any Windows line endings to Unix (if needed)
    sed -i 's/\r$//' entrypoint.sh scripts/*.sh || true

# Create app directories with proper permissions for codex user
RUN mkdir -p /app/data /app/config /app/sessions /app/data/agents /app/data/metadata \
    && chown -R codex:codex /app \
    && chmod -R 755 /app

# Expose port for MCP server
EXPOSE 8210

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; from src.mcp_server import health_check; asyncio.run(health_check())"

# Start the MCP server - try entrypoint script first, fallback to inline commands
ENTRYPOINT ["bash", "-c", "if [ -f ./entrypoint.sh ] && [ -x ./entrypoint.sh ]; then exec ./entrypoint.sh \"$@\"; else mkdir -p /app/data/agents /app/data/metadata /app/config /app/sessions && chmod -R 755 /app/data /app/config /app/sessions && echo 'Codex CLI MCP Server starting...' && exec python server.py \"$@\"; fi"]