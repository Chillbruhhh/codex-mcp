#!/usr/bin/env python3
"""
Simple OAuth Authentication CLI - Fallback version

This is a simplified version that checks dependencies and provides
clear error messages for missing requirements.
"""

import sys
import os
from pathlib import Path

def check_and_install_dependencies():
    """Check for required dependencies and offer to install them."""
    print("🔍 Checking dependencies...")

    missing_packages = []
    required_packages = ["aiohttp", "structlog", "pydantic", "tomli", "python-dotenv"]

    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        print("\n💡 Install missing packages:")
        print(f"   pip install {' '.join(missing_packages)}")

        response = input("\nInstall now? (y/N): ").strip().lower()
        if response == 'y':
            import subprocess
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
                print("✅ Packages installed successfully!")
                return True
            except subprocess.CalledProcessError as e:
                print(f"❌ Installation failed: {e}")
                return False
        else:
            return False

    return True

def main():
    """Main entry point."""
    print("🤖 Codex CLI MCP Server - OAuth Authentication")
    print("=" * 50)

    # Check if we're in the right directory
    current_dir = Path(__file__).parent
    src_dir = current_dir / "src"

    if not src_dir.exists():
        print("❌ Error: 'src' directory not found")
        print(f"📍 Current location: {current_dir}")
        print("💡 Make sure you're running this from the project root directory")
        return 1

    # Check dependencies
    if not check_and_install_dependencies():
        return 1

    # Add directories to path
    sys.path.insert(0, str(src_dir))
    sys.path.insert(0, str(current_dir))

    try:
        # Import after adding paths
        import asyncio
        from cli_auth import main as cli_main

        print("✅ All dependencies available, starting authentication CLI...")
        return asyncio.run(cli_main())

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Check if all files are present:")

        required_files = [
            "src/cli_auth.py",
            "src/oauth_manager.py",
            "src/oauth_flow.py",
            "src/auth_manager.py",
            "src/utils/config.py"
        ]

        for file_path in required_files:
            full_path = current_dir / file_path
            exists = "✅" if full_path.exists() else "❌"
            print(f"   {exists} {file_path}")

        print("\n2. Try installing in development mode:")
        print("   pip install -e .")

        print("\n3. Or run dependency check:")
        print("   python check_dependencies.py")

        return 1

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
        sys.exit(1)