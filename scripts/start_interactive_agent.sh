#!/bin/bash

# Interactive Codex CLI Agent Startup Script
# This starts a persistent Codex CLI agent that receives messages via named pipes
# and logs all conversation activity for visibility

set -e

echo "=================================="
echo "🤖 Starting Interactive Codex CLI Agent"
echo "=================================="

# Setup directories
mkdir -p /tmp/codex_pipes
mkdir -p /tmp/codex_logs

# Create named pipes for communication
PIPE_IN="/tmp/codex_pipes/messages_in"
PIPE_OUT="/tmp/codex_pipes/messages_out"

# Remove old pipes if they exist
rm -f "$PIPE_IN" "$PIPE_OUT"

# Create new named pipes
mkfifo "$PIPE_IN"
mkfifo "$PIPE_OUT"

echo "📁 Working directory: /app/workspace"
echo "📝 Input pipe: $PIPE_IN"
echo "📤 Output pipe: $PIPE_OUT"
echo "🔧 Model: ${CODEX_MODEL:-gpt-4}"
echo "=================================="

# Change to workspace directory
cd /app/workspace

echo "🚀 Launching interactive Codex CLI agent..."
echo "You should see the agent conversation below:"
echo "=================================="

# Function to handle cleanup on exit
cleanup() {
    echo "🛑 Shutting down interactive agent..."
    rm -f "$PIPE_IN" "$PIPE_OUT"
    exit 0
}
trap cleanup SIGTERM SIGINT

# Start Codex CLI in interactive mode with pipes
# This creates a persistent agent that can receive messages
(
    # Monitor input pipe and send messages to Codex CLI
    while true; do
        if read -r message < "$PIPE_IN"; then
            echo "👤 USER MESSAGE: $message"
            echo "$message"
        fi
    done
) | (
    # Start Codex CLI interactively and capture both input and output
    codex --interactive --model "${CODEX_MODEL:-gpt-4}" --no-git-check 2>&1 | tee -a /tmp/codex_logs/conversation.log | while IFS= read -r line; do
        # Log each line from Codex CLI with timestamp and prefix
        echo "🤖 CODEX: $line"

        # Also send to output pipe for MCP server to read
        echo "$line" > "$PIPE_OUT" 2>/dev/null || true
    done
) &

# Store the background process PID
CODEX_PID=$!

echo "✅ Interactive Codex CLI agent started (PID: $CODEX_PID)"
echo "📡 Ready to receive messages via: $PIPE_IN"
echo "📻 Responses available via: $PIPE_OUT"
echo "=================================="
echo "🔍 Watching for conversation activity..."
echo "=================================="

# Keep the script running and monitoring
while kill -0 $CODEX_PID 2>/dev/null; do
    # Check if agent is still responsive
    if [ ! -p "$PIPE_IN" ] || [ ! -p "$PIPE_OUT" ]; then
        echo "❌ Communication pipes lost, restarting..."
        break
    fi

    # Heartbeat every 30 seconds
    sleep 30
    echo "💓 Agent heartbeat - PID $CODEX_PID still active"
done

echo "⚠️ Interactive Codex CLI agent stopped"
cleanup