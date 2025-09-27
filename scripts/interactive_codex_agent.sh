#!/bin/bash

# 🤖 Interactive Codex CLI Agent - Persistent Session Manager
# This creates a continuously running Codex CLI agent that shows all conversation
# activity in Docker logs and communicates via message files for MCP integration

set -e

# Colors and formatting for Docker logs
export BOLD='\033[1m'
export GREEN='\033[0;32m'
export BLUE='\033[0;34m'
export YELLOW='\033[1;33m'
export RED='\033[0;31m'
export NC='\033[0m' # No Color

# Configuration
WORKSPACE_DIR="${WORKSPACE_DIR:-/app/workspace}"
MODEL="${CODEX_MODEL:-gpt-4}"
SESSION_ID="${SESSION_ID:-codex-session}"
MESSAGE_DIR="/tmp/codex_messages"
LOG_FILE="/tmp/codex.log"

# Setup message communication
mkdir -p "$MESSAGE_DIR"
chmod 755 "$MESSAGE_DIR"

# Message files for communication
INCOMING_MSG="$MESSAGE_DIR/incoming.msg"
RESPONSE_MSG="$MESSAGE_DIR/response.msg"
STATUS_FILE="$MESSAGE_DIR/status"

# Cleanup old files
rm -f "$INCOMING_MSG" "$RESPONSE_MSG" "$STATUS_FILE" "$LOG_FILE"

echo -e "${BOLD}=================================="
echo -e "🤖 Interactive Codex CLI Agent"
echo -e "=================================="
echo -e "${GREEN}📁 Workspace: $WORKSPACE_DIR${NC}"
echo -e "${GREEN}🔧 Model: $MODEL${NC}"
echo -e "${GREEN}🆔 Session: $SESSION_ID${NC}"
echo -e "${GREEN}📨 Message Dir: $MESSAGE_DIR${NC}"
echo -e "${BOLD}==================================${NC}"

# Change to workspace directory
cd "$WORKSPACE_DIR" || {
    echo -e "${RED}❌ Failed to access workspace directory: $WORKSPACE_DIR${NC}"
    exit 1
}

echo -e "${YELLOW}🚀 Starting persistent Codex CLI agent...${NC}"
echo -e "${YELLOW}💬 All conversation will appear below:${NC}"
echo -e "${BOLD}==================================${NC}"

# Function to send status updates
update_status() {
    echo "$1" > "$STATUS_FILE"
    echo -e "${BLUE}📊 STATUS: $1${NC}"
}

# Signal handlers for graceful shutdown
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down interactive Codex CLI agent...${NC}"
    update_status "shutting_down"

    if [ -n "$CODEX_PID" ] && kill -0 "$CODEX_PID" 2>/dev/null; then
        echo -e "${YELLOW}Terminating Codex CLI process (PID: $CODEX_PID)${NC}"
        kill -TERM "$CODEX_PID" 2>/dev/null || true
        sleep 2
        kill -KILL "$CODEX_PID" 2>/dev/null || true
    fi

    rm -f "$INCOMING_MSG" "$RESPONSE_MSG" "$STATUS_FILE" "$LOG_FILE"
    echo -e "${GREEN}✅ Cleanup complete${NC}"
    exit 0
}

trap cleanup SIGTERM SIGINT EXIT

# Update initial status
update_status "initializing"

# Start Codex CLI in interactive mode with full logging
echo -e "${GREEN}🎯 Launching interactive Codex CLI with model: $MODEL${NC}"

# Create a co-process to handle Codex CLI interaction
coproc CODEX_PROC (
    # Launch Codex CLI interactively
    exec codex 2>&1
)

# Get the process ID of the Codex CLI
CODEX_PID=$!

# Redirect Codex CLI output to both log file and stdout with formatting
exec 3<&${CODEX_PROC[0]}  # Read from Codex CLI stdout
exec 4>&${CODEX_PROC[1]}  # Write to Codex CLI stdin

echo -e "${GREEN}✅ Codex CLI process started (PID: $CODEX_PID)${NC}"
update_status "agent_ready"

# Function to send a message to Codex CLI
send_to_codex() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    echo -e "${BOLD}${BLUE}👤 USER [$timestamp]: ${NC}$message"
    echo "$message" >&4  # Send to Codex CLI stdin

    # Log to file as well
    echo "[$timestamp] USER: $message" >> "$LOG_FILE"
}

# Function to read response from Codex CLI
read_from_codex() {
    local response=""
    local line=""
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Read response from Codex CLI with timeout
    while IFS= read -t 30 -r line <&3; do
        echo -e "${BOLD}${GREEN}🤖 CODEX [$timestamp]: ${NC}$line"
        response="$response$line\n"

        # Log to file
        echo "[$timestamp] CODEX: $line" >> "$LOG_FILE"

        # Check if this looks like the end of a response
        if [[ "$line" =~ (anything else|help you|let me know|ready for|complete) ]]; then
            break
        fi
    done

    # Write response to response file for MCP server to read
    echo -e "$response" > "$RESPONSE_MSG"
    chmod 644 "$RESPONSE_MSG"
}

# Send initial greeting to Codex CLI
send_to_codex "Hello! I'm ready to collaborate on this project. I can see the workspace at $WORKSPACE_DIR and I'm here to help with any development tasks."

# Read initial response
read_from_codex

echo -e "${YELLOW}💫 Interactive agent is now ready for messages!${NC}"
echo -e "${YELLOW}📝 Send messages by writing to: $INCOMING_MSG${NC}"
echo -e "${YELLOW}📖 Read responses from: $RESPONSE_MSG${NC}"
echo -e "${BOLD}==================================${NC}"

# Main message processing loop
while true; do
    # Check if Codex CLI process is still running
    if ! kill -0 "$CODEX_PID" 2>/dev/null; then
        echo -e "${RED}❌ Codex CLI process died unexpectedly${NC}"
        update_status "agent_failed"
        break
    fi

    # Update status to show we're waiting for messages
    update_status "waiting_for_message"

    # Check for incoming messages
    if [ -f "$INCOMING_MSG" ]; then
        # Read the message
        MESSAGE=$(cat "$INCOMING_MSG" 2>/dev/null || echo "")

        if [ -n "$MESSAGE" ] && [ "$MESSAGE" != "PROCESSED" ]; then
            # Mark message as being processed
            echo "PROCESSING" > "$INCOMING_MSG"

            # Update status
            update_status "processing_message"

            # Send message to Codex CLI
            send_to_codex "$MESSAGE"

            # Read response from Codex CLI
            read_from_codex

            # Mark message as processed
            echo "PROCESSED" > "$INCOMING_MSG"

            echo -e "${YELLOW}✅ Message processed and response ready${NC}"
        fi
    fi

    # Small sleep to avoid busy waiting
    sleep 1
done

echo -e "${RED}❌ Interactive agent loop ended${NC}"
update_status "agent_stopped"