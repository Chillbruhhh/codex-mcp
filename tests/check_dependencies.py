#!/usr/bin/env python3
"""
Check if all required dependencies are available for OAuth authentication.
"""

import sys
from pathlib import Path

def check_dependencies():
    """Check if all required dependencies are available."""
    print("🔍 Checking OAuth Authentication Dependencies")
    print("=" * 50)

    missing_packages = []
    # Format: (pip_name, import_name)
    required_packages = [
        ("aiohttp", "aiohttp"),
        ("structlog", "structlog"),
        ("pydantic", "pydantic"),
        ("tomli", "tomli"),
        ("python-dotenv", "dotenv")
    ]

    print("\n📦 Checking Python packages...")
    for pip_name, import_name in required_packages:
        try:
            __import__(import_name)
            print(f"   ✅ {pip_name}")
        except ImportError:
            print(f"   ❌ {pip_name} - MISSING")
            missing_packages.append(pip_name)

    print("\n📁 Checking project files...")
    current_dir = Path(__file__).parent
    src_dir = current_dir / "src"

    required_files = [
        "src/oauth_manager.py",
        "src/oauth_flow.py",
        "src/cli_auth.py",
        "src/auth_manager.py",
        "src/utils/config.py"
    ]

    missing_files = []
    for file_path in required_files:
        full_path = current_dir / file_path
        if full_path.exists():
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} - MISSING")
            missing_files.append(file_path)

    print("\n" + "=" * 50)
    if missing_packages:
        print("❌ Missing Python packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n💡 Install missing packages:")
        print(f"   pip install {' '.join(missing_packages)}")

    if missing_files:
        print("❌ Missing project files:")
        for file_path in missing_files:
            print(f"   - {file_path}")

    if not missing_packages and not missing_files:
        print("✅ All dependencies are available!")
        print("\n💡 You can now run:")
        print("   python auth.py login")
        return True
    else:
        return False

if __name__ == "__main__":
    success = check_dependencies()
    sys.exit(0 if success else 1)