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
chmod -R 755 /app/data /app/config /app/sessions || true

echo "Directory initialization complete:"
echo "  - /app/data/agents"
echo "  - /app/data/metadata"
echo "  - /app/config"
echo "  - /app/sessions"

# Synchronize Codex auth tokens if provided
AUTH_SOURCE_DIR="${CODEX_AUTH_DIR:-/codex-auth}"
AUTH_SOURCE_FILE="$AUTH_SOURCE_DIR/auth.json"
DEST_DIR="/root/.codex"
DEST_FILE="$DEST_DIR/auth.json"
CONFIG_FILE="/app/config/auth.json"

mkdir -p "$DEST_DIR" /app/config

if [ -f "$AUTH_SOURCE_FILE" ] && [ "$AUTH_SOURCE_FILE" != "$DEST_FILE" ]; then
  echo "Syncing Codex auth tokens from $AUTH_SOURCE_FILE"
  cp "$AUTH_SOURCE_FILE" "$DEST_FILE"
  chmod 600 "$DEST_FILE" || true
  cp "$AUTH_SOURCE_FILE" "$CONFIG_FILE"
elif [ -f "$CONFIG_FILE" ]; then
  echo "Using existing Codex auth tokens at $CONFIG_FILE"
  if [ "$CONFIG_FILE" != "$DEST_FILE" ]; then
    cp "$CONFIG_FILE" "$DEST_FILE"
    chmod 600 "$DEST_FILE" || true
  fi
else
  echo "Warning: Codex auth.json not found. OAuth authentication may fail."
fi

# Start the main application
echo "Starting Codex CLI MCP Server..."
exec python server.py "$@"
