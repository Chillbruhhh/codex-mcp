#!/bin/bash
set -e

# Codex CLI MCP Server Entrypoint
# Handles initialization that was previously done by codex-data-init container

echo "Initializing Codex CLI MCP Server..."

# Create necessary directories with proper permissions
echo "Creating data directories..."
mkdir -p /app/data/agents /app/data/metadata /app/config /app/sessions

# Set proper permissions
echo "Setting directory permissions..."
chmod -R 755 /app/data /app/config /app/sessions

echo "Directory initialization complete:"
echo "  - /app/data/agents"
echo "  - /app/data/metadata"
echo "  - /app/config"
echo "  - /app/sessions"

# Start the main application
echo "Starting Codex CLI MCP Server..."
exec python server.py "$@"