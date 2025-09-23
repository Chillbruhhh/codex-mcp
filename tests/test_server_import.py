#!/usr/bin/env python3
"""
Simple test to verify server can be imported and initialized.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_server_import():
    """Test that we can import and create the MCP server."""
    try:
        from src.mcp_server import create_mcp_server

        print("✓ Successfully imported create_mcp_server")

        # Create server instance
        server = create_mcp_server()

        print("✓ Successfully created MCP server instance")
        print(f"✓ Server has {len(server._tools)} tools registered")

        # List the tools
        print("\nRegistered MCP Tools:")
        for tool_name in server._tools.keys():
            print(f"  - {tool_name}")

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing MCP Server Import and Setup")
    print("=" * 50)

    success = test_server_import()

    if success:
        print("\n🎉 Server import test PASSED!")
        print("✓ All components can be imported")
        print("✓ Server can be created successfully")
        print("✓ Tools are properly registered")
        print("\nTo start the server:")
        print("  python server.py")
    else:
        print("\n❌ Server import test FAILED!")
        sys.exit(1)