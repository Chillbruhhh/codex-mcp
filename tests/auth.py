#!/usr/bin/env python3
"""
Codex CLI MCP Server - OAuth Authentication CLI

This script provides a convenient command-line interface for managing
OAuth authentication with your ChatGPT subscription.

Usage:
    python auth.py login          # Authenticate with ChatGPT subscription
    python auth.py login --manual # Manual authentication flow
    python auth.py status         # Check authentication status
    python auth.py logout         # Revoke tokens and logout
    python auth.py refresh        # Refresh OAuth tokens

Examples:
    # Standard OAuth login (opens browser automatically)
    python auth.py login

    # Manual OAuth login (copy-paste URL)
    python auth.py login --manual

    # Check current authentication status
    python auth.py status

    # Logout and revoke tokens
    python auth.py logout

    # Refresh expired tokens
    python auth.py refresh
"""

import sys
import os
from pathlib import Path

# Add src to path for imports
current_dir = Path(__file__).parent
src_dir = current_dir / "src"

if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Also add the current directory to path
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from cli_auth import main
    import asyncio

    if __name__ == "__main__":
        asyncio.run(main())
except ImportError as e:
    print(f"❌ Import error: {e}")
    print(f"📍 Current directory: {current_dir}")
    print(f"📍 Src directory: {src_dir}")
    print(f"📍 Src directory exists: {src_dir.exists()}")

    if src_dir.exists():
        print("📍 Files in src directory:")
        for file in src_dir.iterdir():
            print(f"   - {file.name}")

    print("\n💡 Try running from the project root directory:")
    print(f"   cd {current_dir}")
    print(f"   python auth.py login")
    sys.exit(1)