"""
Workspace detection utility for MCP client integration.

This module provides functionality to detect and validate workspace directories
from MCP client context, enabling direct file system access for collaborative
development between agents.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)


class WorkspaceDetector:
    """
    Detects and validates workspace directories for MCP client integration.

    Provides methods to identify the actual working directory of MCP clients
    so that Codex CLI can operate directly on the client's files and projects.
    """

    def __init__(self):
        """Initialize the workspace detector."""
        self.detected_workspaces: Dict[str, str] = {}

    def detect_client_workspace(
        self,
        session_id: str,
        hints: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Detect the MCP client's actual workspace directory.

        Uses various methods to identify where the client is working:
        1. Explicit workspace path from client context
        2. Current working directory of the MCP server process
        3. Environment variables
        4. Git repository detection
        5. Common project structure patterns

        Args:
            session_id: Session identifier for caching
            hints: Optional hints about workspace location

        Returns:
            str: Absolute path to detected workspace directory, or None
        """
        # Check if already detected for this session
        if session_id in self.detected_workspaces:
            cached_path = self.detected_workspaces[session_id]
            if self.validate_workspace_path(cached_path):
                logger.debug("Using cached workspace path",
                           session_id=session_id,
                           workspace=cached_path)
                return cached_path
            else:
                # Cached path no longer valid, remove it
                del self.detected_workspaces[session_id]

        workspace_candidates = []

        # Method 0: PRIORITY - MCP Client's actual calling directory
        # This is the directory where the user is running MCP commands from
        mcp_client_dir = self._detect_mcp_client_directory()
        if mcp_client_dir:
            workspace_candidates.append(mcp_client_dir)
            logger.info("Found MCP client calling directory",
                       session_id=session_id,
                       mcp_dir=mcp_client_dir)

        # Method 1: Explicit workspace from hints
        if hints and "workspace_dir" in hints:
            workspace_candidates.append(hints["workspace_dir"])

        if hints and "client_cwd" in hints:
            workspace_candidates.append(hints["client_cwd"])

        # Method 2: Current working directory
        try:
            cwd = os.getcwd()
            workspace_candidates.append(cwd)
            logger.debug("Added current working directory as candidate",
                       cwd=cwd)
        except Exception as e:
            logger.debug("Could not get current working directory", error=str(e))

        # Method 3: Environment variables
        env_candidates = [
            os.environ.get("MCP_WORKSPACE"),
            os.environ.get("PROJECT_ROOT"),
            os.environ.get("WORKSPACE_ROOT"),
            os.environ.get("PWD")  # Unix-style current directory
        ]

        for env_path in env_candidates:
            if env_path and os.path.exists(env_path):
                workspace_candidates.append(env_path)

        # Method 4: Git repository detection (walk up from current directory)
        git_root = self._find_git_repository_root()
        if git_root:
            workspace_candidates.append(git_root)

        # Method 5: Project structure detection
        project_root = self._find_project_root()
        if project_root:
            workspace_candidates.append(project_root)

        # Evaluate candidates
        best_workspace = self._evaluate_workspace_candidates(
            workspace_candidates,
            session_id
        )

        if best_workspace:
            # Cache the detected workspace
            self.detected_workspaces[session_id] = best_workspace
            logger.info("Detected client workspace",
                       session_id=session_id,
                       workspace=best_workspace,
                       method="comprehensive_detection")
            return best_workspace

        logger.warning("Could not detect client workspace directory",
                     session_id=session_id,
                     candidates_tried=len(workspace_candidates))
        return None

    def _find_git_repository_root(self, start_path: Optional[str] = None) -> Optional[str]:
        """Find the root of a git repository by walking up the directory tree."""
        current_path = Path(start_path or os.getcwd()).resolve()

        # Walk up the directory tree
        for parent in [current_path] + list(current_path.parents):
            if (parent / ".git").exists():
                logger.debug("Found git repository root", path=str(parent))
                return str(parent)

        return None

    def _find_project_root(self, start_path: Optional[str] = None) -> Optional[str]:
        """Find project root by looking for common project files."""
        current_path = Path(start_path or os.getcwd()).resolve()

        # Common project root indicators
        project_indicators = [
            "package.json",     # Node.js
            "pyproject.toml",   # Python
            "Cargo.toml",       # Rust
            "pom.xml",          # Java Maven
            "build.gradle",     # Java Gradle
            "go.mod",           # Go
            "Gemfile",          # Ruby
            "composer.json",    # PHP
            ".project",         # Generic project file
            "README.md",        # Documentation (weaker indicator)
            "Makefile",         # Build system
            "CMakeLists.txt",   # C/C++ CMake
        ]

        # Walk up the directory tree
        for parent in [current_path] + list(current_path.parents):
            for indicator in project_indicators:
                if (parent / indicator).exists():
                    logger.debug("Found project root indicator",
                               path=str(parent),
                               indicator=indicator)
                    return str(parent)

        return None

    def _evaluate_workspace_candidates(
        self,
        candidates: List[str],
        session_id: str
    ) -> Optional[str]:
        """Evaluate workspace candidates and select the best one."""
        if not candidates:
            return None

        scored_candidates = []

        for candidate in candidates:
            if not candidate:
                continue

            abs_candidate = os.path.abspath(candidate)

            # Validate the path exists and is accessible
            if not self.validate_workspace_path(abs_candidate):
                continue

            # Score the candidate based on various factors
            score = self._score_workspace_candidate(abs_candidate)
            scored_candidates.append((score, abs_candidate))

            logger.debug("Scored workspace candidate",
                       session_id=session_id,
                       candidate=abs_candidate,
                       score=score)

        if not scored_candidates:
            return None

        # Sort by score (highest first) and return the best
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_path = scored_candidates[0]

        logger.info("Selected best workspace candidate",
                   session_id=session_id,
                   workspace=best_path,
                   score=best_score,
                   total_candidates=len(scored_candidates))

        return best_path

    def _score_workspace_candidate(self, path: str) -> int:
        """Score a workspace candidate based on project indicators."""
        score = 0
        path_obj = Path(path)

        # Base score for being a valid directory
        score += 10

        # Bonus for containing a git repository
        if (path_obj / ".git").exists():
            score += 50

        # Bonus for project files (higher scores for stronger indicators)
        project_files = {
            "package.json": 30,
            "pyproject.toml": 30,
            "Cargo.toml": 30,
            "go.mod": 30,
            "pom.xml": 25,
            "build.gradle": 25,
            "Gemfile": 25,
            "composer.json": 25,
            "Makefile": 20,
            "CMakeLists.txt": 20,
            "README.md": 15,
            "README.rst": 15,
            ".gitignore": 10,
            "LICENSE": 10,
        }

        for file_name, file_score in project_files.items():
            if (path_obj / file_name).exists():
                score += file_score

        # Bonus for common project directory structures
        common_dirs = ["src", "lib", "tests", "docs", "scripts"]
        for dir_name in common_dirs:
            if (path_obj / dir_name).exists():
                score += 5

        # Penalty for system directories (we probably don't want these)
        system_dirs = ["/usr", "/var", "/etc", "/tmp", "/sys", "/proc"]
        if any(path.startswith(sys_dir) for sys_dir in system_dirs):
            score -= 100

        # Penalty for being too deep (prefer higher-level directories)
        depth = len(path_obj.parts)
        if depth > 6:  # Arbitrary threshold
            score -= (depth - 6) * 2

        return max(0, score)  # Don't return negative scores

    def validate_workspace_path(self, path: str) -> bool:
        """
        Validate that a workspace path is accessible and suitable.

        Args:
            path: Path to validate

        Returns:
            bool: True if path is valid for use as workspace
        """
        if not path:
            return False

        try:
            abs_path = os.path.abspath(path)

            # Check if path exists and is a directory
            if not os.path.exists(abs_path):
                logger.debug("Workspace path does not exist", path=abs_path)
                return False

            if not os.path.isdir(abs_path):
                logger.debug("Workspace path is not a directory", path=abs_path)
                return False

            # Check if we have read access
            if not os.access(abs_path, os.R_OK):
                logger.debug("No read access to workspace path", path=abs_path)
                return False

            # Check if we have write access (needed for Codex CLI collaboration)
            if not os.access(abs_path, os.W_OK):
                logger.debug("No write access to workspace path", path=abs_path)
                return False

            # Additional safety checks
            # Don't allow system root or other dangerous paths
            dangerous_paths = ["/", "C:\\", "/usr", "/var", "/etc", "/sys", "/proc"]
            for dangerous in dangerous_paths:
                if abs_path == dangerous or abs_path.startswith(dangerous + os.sep):
                    logger.warning("Rejected dangerous workspace path", path=abs_path)
                    return False

            logger.debug("Workspace path validation passed", path=abs_path)
            return True

        except Exception as e:
            logger.error("Error validating workspace path",
                       path=path,
                       error=str(e))
            return False

    def get_workspace_info(self, workspace_path: str) -> Dict[str, Any]:
        """
        Get detailed information about a workspace directory.

        Args:
            workspace_path: Path to analyze

        Returns:
            dict: Workspace information including project type, structure, etc.
        """
        if not self.validate_workspace_path(workspace_path):
            return {"valid": False, "error": "Invalid workspace path"}

        path_obj = Path(workspace_path)
        info = {
            "valid": True,
            "absolute_path": str(path_obj.resolve()),
            "size_mb": self._get_directory_size_mb(workspace_path),
            "file_count": self._count_files(workspace_path),
            "has_git": (path_obj / ".git").exists(),
            "project_types": [],
            "project_files": [],
            "directory_structure": []
        }

        # Detect project types
        project_type_indicators = {
            "Node.js": ["package.json", "node_modules"],
            "Python": ["pyproject.toml", "setup.py", "requirements.txt", "pipfile"],
            "Rust": ["Cargo.toml", "src/main.rs"],
            "Go": ["go.mod", "main.go"],
            "Java": ["pom.xml", "build.gradle", "src/main/java"],
            "C/C++": ["Makefile", "CMakeLists.txt", "src/*.c", "src/*.cpp"],
            "Ruby": ["Gemfile", "lib/"],
            "PHP": ["composer.json", "index.php"]
        }

        for project_type, indicators in project_type_indicators.items():
            if any((path_obj / indicator).exists() for indicator in indicators):
                info["project_types"].append(project_type)

        # List important project files
        try:
            for item in path_obj.iterdir():
                if item.is_file() and item.name.startswith((".", "README", "LICENSE")):
                    info["project_files"].append(item.name)
                elif item.is_dir() and item.name in ["src", "lib", "tests", "docs"]:
                    info["directory_structure"].append(item.name)
        except Exception as e:
            logger.debug("Error reading workspace directory", error=str(e))

        return info

    def _get_directory_size_mb(self, path: str) -> float:
        """Get approximate directory size in MB (limited scan for performance)."""
        try:
            total_size = 0
            file_count = 0
            max_files = 1000  # Limit scan for performance

            for root, dirs, files in os.walk(path):
                # Skip hidden directories and common large directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'target', 'build']]

                for file in files:
                    file_count += 1
                    if file_count > max_files:
                        break
                    try:
                        total_size += os.path.getsize(os.path.join(root, file))
                    except (OSError, IOError):
                        continue

                if file_count > max_files:
                    break

            return round(total_size / (1024 * 1024), 2)
        except Exception:
            return 0.0

    def _count_files(self, path: str) -> int:
        """Count files in directory (approximate, for performance)."""
        try:
            count = 0
            max_count = 1000  # Limit for performance

            for root, dirs, files in os.walk(path):
                # Skip hidden and large directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'target', 'build']]
                count += len(files)
                if count > max_count:
                    return max_count

            return count
        except Exception:
            return 0

    def clear_cached_workspace(self, session_id: str) -> None:
        """Clear cached workspace for a session."""
        if session_id in self.detected_workspaces:
            del self.detected_workspaces[session_id]
            logger.debug("Cleared cached workspace", session_id=session_id)

    def list_cached_workspaces(self) -> Dict[str, str]:
        """List all cached workspace detections."""
        return self.detected_workspaces.copy()

    def _detect_mcp_client_directory(self) -> Optional[str]:
        """
        Detect the directory where the MCP client is actually being run from.

        This is the key method to find the REAL workspace directory that the
        user is working in when they run MCP commands.
        """
        # Method 1: Check for MCP-specific environment variables
        mcp_client_vars = [
            "MCP_CLIENT_DIR",
            "MCP_WORKSPACE",
            "CLIENT_WORKSPACE_DIR"
        ]

        for var in mcp_client_vars:
            if var in os.environ:
                client_dir = os.environ[var]
                if self.validate_workspace_path(client_dir):
                    logger.debug("Found MCP client directory from environment",
                               env_var=var,
                               directory=client_dir)
                    return client_dir

        # Method 2: Process inspection - look at parent processes
        try:
            import psutil
            current_process = psutil.Process()

            # Walk up the process tree to find the MCP client
            for parent in current_process.parents():
                try:
                    # Check if this could be the MCP client process
                    if any(mcp_indicator in parent.name().lower() for mcp_indicator in
                           ['claude', 'mcp', 'client']):
                        parent_cwd = parent.cwd()
                        if self.validate_workspace_path(parent_cwd):
                            logger.debug("Found MCP client directory from process tree",
                                       process_name=parent.name(),
                                       directory=parent_cwd)
                            return parent_cwd
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except ImportError:
            logger.debug("psutil not available for process inspection")
        except Exception as e:
            logger.debug("Process inspection failed", error=str(e))

        # Method 3: Check current working directory with scoring
        try:
            cwd = os.getcwd()
            if self.validate_workspace_path(cwd):
                # Score the current directory to see if it looks like a real project
                score = self._score_workspace_candidate(cwd)
                if score > 20:  # Reasonable project threshold
                    logger.debug("Using current working directory as MCP client dir",
                               directory=cwd,
                               score=score)
                    return cwd
        except Exception as e:
            logger.debug("Could not check current working directory", error=str(e))

        # Method 4: Check parent directories for project indicators
        try:
            current_path = Path.cwd()
            for parent in [current_path] + list(current_path.parents)[:3]:  # Check up to 3 levels
                parent_str = str(parent)
                if self.validate_workspace_path(parent_str):
                    score = self._score_workspace_candidate(parent_str)
                    if score > 30:  # Higher threshold for parent dirs
                        logger.debug("Found project directory in parent path",
                                   directory=parent_str,
                                   score=score)
                        return parent_str
        except Exception as e:
            logger.debug("Parent directory check failed", error=str(e))

        logger.debug("Could not detect MCP client calling directory")
        return None


# Global instance for use across modules
workspace_detector = WorkspaceDetector()