#!/usr/bin/env python3
"""
Debug Codex CLI installation and PATH issues.
"""

import subprocess
import sys
import os
from pathlib import Path

def check_command_variations():
    """Check different possible Codex CLI command names."""
    print("🔍 Checking for Codex CLI variants...")

    possible_commands = [
        "codex",
        "codex.exe",
        "codex-cli",
        "codex-cli.exe",
        "@openai/codex",
        "npx codex",
        "npx @openai/codex"
    ]

    found_commands = []

    for cmd in possible_commands:
        try:
            if cmd.startswith("npx"):
                # For npx commands, split into parts
                cmd_parts = cmd.split()
                result = subprocess.run(cmd_parts + ["--version"],
                                      capture_output=True, text=True, timeout=10)
            else:
                result = subprocess.run([cmd, "--version"],
                                      capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                print(f"   ✅ {cmd}: {result.stdout.strip()}")
                found_commands.append(cmd)
            else:
                print(f"   ❌ {cmd}: Exit code {result.returncode}")

        except FileNotFoundError:
            print(f"   ❌ {cmd}: Not found")
        except subprocess.TimeoutExpired:
            print(f"   ⏰ {cmd}: Timeout")
        except Exception as e:
            print(f"   ❌ {cmd}: Error - {e}")

    return found_commands

def check_node_and_npm():
    """Check Node.js and npm installation."""
    print("\n🔍 Checking Node.js environment...")

    try:
        # Check Node.js
        result = subprocess.run(["node", "--version"],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"   ✅ Node.js: {result.stdout.strip()}")
        else:
            print(f"   ❌ Node.js: Exit code {result.returncode}")
    except Exception as e:
        print(f"   ❌ Node.js: {e}")

    try:
        # Check npm
        result = subprocess.run(["npm", "--version"],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"   ✅ npm: {result.stdout.strip()}")
        else:
            print(f"   ❌ npm: Exit code {result.returncode}")
    except Exception as e:
        print(f"   ❌ npm: {e}")

def check_npm_global_packages():
    """Check globally installed npm packages."""
    print("\n🔍 Checking global npm packages...")

    try:
        result = subprocess.run(["npm", "list", "-g", "--depth=0"],
                              capture_output=True, text=True, timeout=10)

        if "codex" in result.stdout.lower() or "@openai/codex" in result.stdout.lower():
            print("   ✅ Found Codex-related packages:")
            for line in result.stdout.split('\n'):
                if 'codex' in line.lower():
                    print(f"      {line.strip()}")
        else:
            print("   ❌ No Codex packages found in global npm packages")
            print("   📋 All global packages:")
            for line in result.stdout.split('\n')[:10]:  # Show first 10 lines
                if line.strip() and not line.startswith('npm'):
                    print(f"      {line.strip()}")

    except Exception as e:
        print(f"   ❌ Error checking npm packages: {e}")

def check_path_environment():
    """Check PATH environment variable."""
    print("\n🔍 Checking PATH environment...")

    path_var = os.environ.get('PATH', '')
    path_dirs = path_var.split(os.pathsep)

    print(f"   📍 PATH contains {len(path_dirs)} directories")

    # Look for npm/node related directories
    npm_dirs = [d for d in path_dirs if 'npm' in d.lower() or 'node' in d.lower()]
    if npm_dirs:
        print("   📁 Node/npm related directories in PATH:")
        for dir_path in npm_dirs[:5]:  # Show first 5
            print(f"      {dir_path}")

    # Check for common npm global install locations
    common_npm_paths = [
        os.path.expanduser("~\\AppData\\Roaming\\npm"),
        os.path.expanduser("~\\AppData\\Local\\npm"),
        "C:\\Program Files\\nodejs",
        "C:\\Users\\%USERNAME%\\AppData\\Roaming\\npm"
    ]

    print("\n   🔍 Checking common npm global locations:")
    for path_str in common_npm_paths:
        path_obj = Path(os.path.expandvars(path_str))
        if path_obj.exists():
            print(f"      ✅ {path_obj}")
            # Look for codex in this directory
            codex_files = list(path_obj.glob("*codex*"))
            if codex_files:
                print(f"         📁 Found: {[f.name for f in codex_files]}")
        else:
            print(f"      ❌ {path_obj}")

def main():
    """Main debug function."""
    print("🤖 Codex CLI Debug Tool")
    print("=" * 30)

    # Check command variations
    found_commands = check_command_variations()

    # Check Node.js environment
    check_node_and_npm()

    # Check npm packages
    check_npm_global_packages()

    # Check PATH
    check_path_environment()

    print("\n" + "=" * 50)
    print("📋 Summary:")

    if found_commands:
        print(f"✅ Found working Codex commands: {', '.join(found_commands)}")
        print("\n💡 Try using one of these commands:")
        for cmd in found_commands:
            print(f"   {cmd} --version")
    else:
        print("❌ No working Codex CLI commands found")
        print("\n💡 Possible solutions:")
        print("1. Reinstall Codex CLI: npm install -g @openai/codex")
        print("2. Use npx: npx @openai/codex --version")
        print("3. Check if PATH includes npm global directory")
        print("4. Restart terminal after installation")

if __name__ == "__main__":
    main()