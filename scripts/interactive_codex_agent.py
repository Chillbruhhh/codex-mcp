#!/usr/bin/env python3
"""Persistent Codex proto bridge.

Runs inside the agent container, launches ``codex proto`` and proxies
json-line submissions and events through simple FIFO message pipes so the
MCP server can cooperate with a long-lived Codex session.
"""

import asyncio
import json
import os
import shutil
import stat
import time
import uuid
from pathlib import Path
from typing import Optional

WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", "/app/workspace"))
MESSAGE_DIR = Path("/tmp/codex_messages")
INCOMING_PATH = MESSAGE_DIR / "incoming.msg"
RESPONSE_PATH = MESSAGE_DIR / "response.msg"
STATUS_PATH = MESSAGE_DIR / "status"
EVENT_LOG_PATH = MESSAGE_DIR / "events.log"

STATUS_INITIALIZING = "initializing"
STATUS_AGENT_READY = "agent_ready"
STATUS_WAITING = "waiting_for_message"
STATUS_PROCESSING = "processing"
STATUS_FAILED = "agent_failed"
STATUS_SHUTTING_DOWN = "shutting_down"

HOME_PATH = Path.home()
EFFECTIVE_HOME_PATH = Path(os.environ.get("CODEX_REAL_HOME") or "/home/codex")

HOME_AUTH_PATH = HOME_PATH / ".codex" / "auth.json"
CONFIG_HOME_DIR = HOME_PATH / ".config" / "codex"
CONFIG_AUTH_PATH = CONFIG_HOME_DIR / "auth.json"
CONFIG_TARGET_PATH = CONFIG_HOME_DIR / "config.toml"

SYSTEM_AUTH_PATH = EFFECTIVE_HOME_PATH / ".codex" / "auth.json"
SYSTEM_CONFIG_DIR = EFFECTIVE_HOME_PATH / ".config" / "codex"
SYSTEM_CONFIG_PATH = SYSTEM_CONFIG_DIR / "config.toml"
CONFIG_SOURCE_CANDIDATES = []

config_env_path = os.environ.get("CODEX_CONFIG_PATH")
if config_env_path:
    CONFIG_SOURCE_CANDIDATES.append(Path(config_env_path))
CONFIG_SOURCE_CANDIDATES.append(Path("/app/config/config.toml"))

AUTH_SOURCE_PATHS = [
    Path("/app/.codex/auth.json"),
    Path("/app/config/auth.json"),
    Path("/home/codex/.codex/auth.json"),
    HOME_AUTH_PATH,
    Path("/root/.codex/auth.json"),
]
AUTH_TARGET_PATH = HOME_AUTH_PATH


def log(message: str) -> None:
    """Write container-visible log entry."""
    print(message, flush=True)


def update_status(state: str) -> None:
    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(state)
    except PermissionError as exc:
        log(f"Warning: failed to write status file {STATUS_PATH}: {exc}")
    except OSError as exc:
        log(f"Warning: error writing status file {STATUS_PATH}: {exc}")
    log(f"[STATUS] {state}")


def copy_auth_if_available() -> None:
    """Copy auth.json from known locations into the Codex home if present."""
    for candidate in AUTH_SOURCE_PATHS:
        try:
            if not candidate.exists():
                log(f"Auth source {candidate} not present")
                continue
        except PermissionError as exc:
            log(f"Skipping auth source {candidate}: permission denied ({exc})")
            continue
        except OSError as exc:
            log(f"Skipping auth source {candidate}: {exc}")
            continue

        try:
            candidate_path = candidate.resolve()
        except (PermissionError, OSError):
            candidate_path = candidate

        try:
            target_path = AUTH_TARGET_PATH.resolve()
        except (PermissionError, OSError):
            target_path = AUTH_TARGET_PATH

        if candidate_path == target_path:
            log(f"auth.json already present at {candidate}")
            apply_auth_environment()
            return

        for target_path in {AUTH_TARGET_PATH, SYSTEM_AUTH_PATH}:
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError as exc:
                log(f"Warning: cannot create auth directory {target_path.parent}: {exc}")
                continue
            except OSError as exc:
                log(f"Warning: failed to prepare auth directory {target_path.parent}: {exc}")
                continue

        try:
            content = candidate.read_text()
        except PermissionError as exc:
            log(f"Warning: cannot read auth.json from {candidate}: {exc}")
            continue
        except OSError as exc:
            log(f"Warning: error reading auth.json from {candidate}: {exc}")
            continue

        wrote_any = False
        for target_path in {AUTH_TARGET_PATH, SYSTEM_AUTH_PATH}:
            try:
                target_path.write_text(content)
                os.chmod(target_path, 0o600)
                wrote_any = True
                log(f"Copied auth.json from {candidate} to {target_path}")
            except PermissionError as exc:
                log(f"Warning: failed to write auth.json to {target_path}: {exc}")
            except OSError as exc:
                log(f"Warning: error writing auth.json to {target_path}: {exc}")

        if wrote_any:
            try:
                for config_path in {CONFIG_AUTH_PATH, SYSTEM_CONFIG_DIR / "auth.json"}:
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    config_path.write_text(content)
                    os.chmod(config_path, 0o600)
            except PermissionError as exc:
                log(f"Warning: failed to write config auth file copy: {exc}")
            except OSError as exc:
                log(f"Warning: error writing config auth file copy: {exc}")
            apply_auth_environment()
            return

    api_key = os.getenv("OPENAI_API_KEY")
    access_token = os.getenv("OPENAI_ACCESS_TOKEN") or os.getenv("CHATGPT_OAUTH_TOKEN")

    if api_key or access_token:
        try:
            for target_path in {AUTH_TARGET_PATH, SYSTEM_AUTH_PATH}:
                target_path.parent.mkdir(parents=True, exist_ok=True)

            payload = {
                "OPENAI_API_KEY": api_key,
                "tokens": None,
                "last_refresh": None,
            }
            if access_token:
                payload["OPENAI_API_KEY"] = None
                payload["tokens"] = {
                    "access_token": access_token,
                    "token_type": "Bearer",
                }
            serialized = json.dumps(payload)
            wrote_any = False
            for target_path in {AUTH_TARGET_PATH, SYSTEM_AUTH_PATH}:
                try:
                    target_path.write_text(serialized)
                    os.chmod(target_path, 0o600)
                    wrote_any = True
                    log(f"Synthesized auth.json at {target_path}")
                except PermissionError as exc:
                    log(f"Warning: failed to write synthesized auth.json to {target_path}: {exc}")
                except OSError as exc:
                    log(f"Warning: error writing synthesized auth.json to {target_path}: {exc}")

            if wrote_any:
                try:
                    for config_path in {CONFIG_AUTH_PATH, SYSTEM_CONFIG_DIR / "auth.json"}:
                        config_path.parent.mkdir(parents=True, exist_ok=True)
                        config_path.write_text(serialized)
                        os.chmod(config_path, 0o600)
                except PermissionError as exc:
                    log(f"Warning: failed to write config auth copy: {exc}")
                except OSError as exc:
                    log(f"Warning: error writing config auth copy: {exc}")

                log("Synthesized auth.json from environment variables")
                apply_auth_environment()
                return
        except PermissionError as exc:
            log(f"Warning: failed to synthesize auth.json: {exc}")
        except OSError as exc:
            log(f"Warning: error synthesizing auth.json: {exc}")

    log("Warning: no auth.json found; Codex will run unauthenticated")


def apply_auth_environment() -> None:
    """Apply environment variables based on auth.json contents."""
    for source in (SYSTEM_AUTH_PATH, AUTH_TARGET_PATH, CONFIG_AUTH_PATH, SYSTEM_CONFIG_DIR / "auth.json"):
        if source.exists():
            break
    else:
        log("Auth file not found; cannot set environment")
        return

    try:
        data = json.loads(source.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log(f"Warning: failed to parse auth.json for environment setup: {exc}")
        return

    api_key = data.get("OPENAI_API_KEY")
    tokens = data.get("tokens") or {}
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None

    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        log("Applied OPENAI_API_KEY from auth.json")

    if access_token:
        os.environ["OPENAI_ACCESS_TOKEN"] = access_token
        log("Applied OPENAI_ACCESS_TOKEN from auth.json")


def copy_config_if_available() -> None:
    """Ensure Codex config file is available in the expected location."""
    for candidate in CONFIG_SOURCE_CANDIDATES:
        if not candidate:
            continue
        try:
            if not candidate.exists():
                continue
        except PermissionError as exc:
            log(f"Skipping config source {candidate}: permission denied ({exc})")
            continue
        except OSError as exc:
            log(f"Skipping config source {candidate}: {exc}")
            continue

        wrote_any = False
        for target_dir, target_path in (
            (CONFIG_HOME_DIR, CONFIG_TARGET_PATH),
            (SYSTEM_CONFIG_DIR, SYSTEM_CONFIG_PATH),
        ):
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError as exc:
                log(f"Warning: cannot create config directory {target_dir}: {exc}")
                continue
            except OSError as exc:
                log(f"Warning: failed to prepare config directory {target_dir}: {exc}")
                continue

            try:
                shutil.copy2(candidate, target_path)
                log(f"Copied config.toml from {candidate} to {target_path}")
                wrote_any = True
            except PermissionError as exc:
                log(f"Warning: failed to copy config.toml to {target_path}: {exc}")
            except OSError as exc:
                log(f"Warning: error copying config.toml to {target_path}: {exc}")

        if wrote_any:
            return

    # Generate minimal config referencing environment-managed API key
    default_config = (
        "model = \"gpt-5-codex\"\n"
        "provider = \"openai\"\n"
        "approvalMode = \"suggest\"\n"
        "fullAutoErrorMode = \"ask-user\"\n"
        "notify = false\n\n"
        "[providers.openai]\n"
        "name = \"OpenAI\"\n"
        "baseURL = \"https://api.openai.com/v1\"\n"
        "envKey = \"OPENAI_API_KEY\"\n"
    )

    for target_dir, target_path in (
        (CONFIG_HOME_DIR, CONFIG_TARGET_PATH),
        (SYSTEM_CONFIG_DIR, SYSTEM_CONFIG_PATH),
    ):
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path.write_text(default_config)
            log(f"Wrote default config.toml to {target_path}")
        except PermissionError as exc:
            log(f"Warning: failed to write default config.toml to {target_path}: {exc}")
        except OSError as exc:
            log(f"Warning: error writing default config.toml to {target_path}: {exc}")


def ensure_message_channels() -> None:
    """Ensure FIFO/message files are ready for Codex communication."""
    MESSAGE_DIR.mkdir(parents=True, exist_ok=True)

    if INCOMING_PATH.exists():
        try:
            mode = os.stat(INCOMING_PATH).st_mode
            if not stat.S_ISFIFO(mode):
                INCOMING_PATH.unlink()
                os.mkfifo(INCOMING_PATH, 0o600)
        except FileNotFoundError:
            os.mkfifo(INCOMING_PATH, 0o600)
        except PermissionError as exc:
            log(f"Warning: cannot prepare incoming FIFO {INCOMING_PATH}: {exc}")
    else:
        try:
            os.mkfifo(INCOMING_PATH, 0o600)
        except PermissionError as exc:
            log(f"Warning: failed to create incoming FIFO {INCOMING_PATH}: {exc}")

    # Response/status/event files can be regular files
    RESPONSE_PATH.touch(exist_ok=True)
    STATUS_PATH.write_text(STATUS_INITIALIZING)
    EVENT_LOG_PATH.touch(exist_ok=True)


async def launch_codex_process() -> asyncio.subprocess.Process:
    """Launch the Codex CLI proto process."""
    log("Launching codex proto process")
    try:
        proc = await asyncio.create_subprocess_exec(
            "codex",
            "proto",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKSPACE_DIR),
            env=os.environ.copy(),
        )
        log(f"codex proto started (pid={proc.pid})")
        return proc
    except FileNotFoundError:
        update_status(STATUS_FAILED)
        log("Error: codex binary not found in PATH")
        raise
    except Exception as exc:
        update_status(STATUS_FAILED)
        log(f"Error launching codex proto: {exc}")
        raise


def append_event_log(raw_line: str) -> None:
    with EVENT_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(raw_line + "\n")


def blocking_read_fifo() -> Optional[str]:
    """Blocking read on the incoming FIFO executed in a worker thread."""
    try:
        with INCOMING_PATH.open("r", encoding="utf-8") as fifo:
            data = fifo.read()
            return data
    except FileNotFoundError:
        return None


class ResponseAggregator:
    """Tracks the latest submission's textual response for the MCP server."""

    def __init__(self) -> None:
        self.current_submission: Optional[str] = None
        self.buffers: dict[str, str] = {}
        self.ready: dict[str, bool] = {}
        self.reasoning_buffers: dict[str, str] = {}

    def _resolve_submission(self, submission_id: Optional[str]) -> Optional[str]:
        """Map proto event identifiers back to the active submission."""
        if submission_id and submission_id in self.buffers:
            return submission_id
        return self.current_submission

    def begin_submission(self, submission_id: str) -> None:
        self.current_submission = submission_id
        self.buffers[submission_id] = ""
        self.ready[submission_id] = False
        RESPONSE_PATH.write_text("PROCESSING")

    def append_delta(self, submission_id: str, delta: str) -> None:
        target_id = self._resolve_submission(submission_id)
        if not target_id:
            return
        if target_id != submission_id:
            self.buffers.setdefault(target_id, "")
        current = self.buffers.get(target_id, "") + delta
        self.buffers[target_id] = current

    def finalize_message(self, submission_id: str, message: str) -> None:
        target_id = self._resolve_submission(submission_id)
        if not target_id:
            return
        reasoning = self.reasoning_buffers.pop(target_id, "")
        existing = self.buffers.get(target_id, "")
        combined = ""
        if reasoning:
            combined += reasoning
            if not reasoning.endswith("\n"):
                combined += "\n"
        if existing:
            combined += existing
            if not existing.endswith("\n"):
                combined += "\n"
        combined += message
        self.buffers[target_id] = existing
        self.buffers[target_id] = combined
        self.mark_ready(target_id)

    def append_system_note(self, text: str) -> None:
        if self.current_submission:
            buf = self.buffers.get(self.current_submission, "") + text
            self.buffers[self.current_submission] = buf
            if self.ready.get(self.current_submission):
                RESPONSE_PATH.write_text(buf)
        else:
            RESPONSE_PATH.write_text(text)

    def clear(self) -> None:
        if self.current_submission and self.current_submission in self.buffers:
            if self.ready.get(self.current_submission):
                RESPONSE_PATH.write_text(self.buffers[self.current_submission])

    def mark_ready(self, submission_id: Optional[str]) -> None:
        target_id = self._resolve_submission(submission_id)
        if not target_id:
            return
        self.ready[target_id] = True
        if target_id == self.current_submission:
            RESPONSE_PATH.write_text(self.buffers.get(target_id, ""))


async def read_stderr(proc: asyncio.subprocess.Process) -> None:
    reader = proc.stderr
    assert reader is not None
    while True:
        line = await reader.readline()
        if not line:
            break
        log(f"[CODEX STDERR] {line.decode('utf-8', errors='replace').rstrip()}")


def handle_event(event: dict, aggregator: ResponseAggregator) -> None:
    event_id = event.get("id", "")
    msg = event.get("msg", {})
    event_type = msg.get("type")
    log(f"[PROTO EVENT] {event_type} ({event_id})")

    if event_type == "session_configured":
        update_status(STATUS_AGENT_READY)
        aggregator.clear()
    elif event_type == "agent_message_delta":
        aggregator.append_delta(event_id, msg.get("delta", ""))
    elif event_type == "agent_message":
        aggregator.finalize_message(event_id, msg.get("message", ""))
        update_status(STATUS_WAITING)
    elif event_type == "task_started":
        aggregator.append_system_note(f"\n[task_started] {msg.get('label', '')}\n")
        update_status(STATUS_PROCESSING)
    elif event_type == "task_complete":
        aggregator.append_system_note("\n[task_complete]\n")
        aggregator.mark_ready(event_id)
        update_status(STATUS_WAITING)
    elif event_type == "error":
        aggregator.append_system_note(f"\n[error] {msg.get('message', 'unknown error')}\n")
        aggregator.mark_ready(event_id)
        update_status(STATUS_FAILED)
    elif event_type in {"agent_reasoning_delta", "agent_reasoning", "agent_reasoning_section_break"}:
        text = msg.get("delta") or msg.get("text") or ""
        if event_type == "agent_reasoning_section_break":
            aggregator.append_system_note("\n")
        elif text:
            aggregator.append_system_note(text)
            current = aggregator.reasoning_buffers.get(event_id, "")
            aggregator.reasoning_buffers[event_id] = current + text
    elif event_type == "user_message":
        pass
    elif event_type == "token_count":
        total = msg.get("total", {})
        aggregator.append_system_note(
            f"\n[token_usage] input={total.get('input_tokens')} output={total.get('output_tokens')}\n"
        )
    elif event_type == "exec_approval_request":
        aggregator.append_system_note("\n[approval_requested] command pending\n")
        update_status(STATUS_PROCESSING)
    elif event_type == "stream_error":
        error_msg = msg.get("error", "stream disconnected")
        aggregator.append_system_note(f"\n[stream_error] {error_msg}\n")
        aggregator.mark_ready(event_id)
        update_status(STATUS_WAITING)


async def fifo_submission_loop(proc: asyncio.subprocess.Process, aggregator: ResponseAggregator) -> None:
    loop = asyncio.get_running_loop()
    writer = proc.stdin
    assert writer is not None
    while True:
        message = await loop.run_in_executor(None, blocking_read_fifo)
        if message is None:
            await asyncio.sleep(0.1)
            continue
        content = message.strip()
        if not content:
            continue
        submission_id = str(uuid.uuid4())
        submission = {
            "id": submission_id,
            "op": {
                "type": "user_input",
                "items": [
                    {
                        "type": "text",
                        "text": content,
                    }
                ],
            },
        }
        payload = json.dumps(submission)
        log(f"[PROTO SUBMIT] {submission_id} -> {content[:80]!r}")
        aggregator.begin_submission(submission_id)
        update_status(STATUS_PROCESSING)
        writer.write((payload + "\n").encode("utf-8"))
        try:
            await writer.drain()
        except ConnectionResetError:
            log("[PROTO] Failed to write submission (stdin closed)")
            break


async def read_event_stream(proc: asyncio.subprocess.Process, aggregator: ResponseAggregator) -> None:
    reader = proc.stdout
    assert reader is not None
    while True:
        line = await reader.readline()
        if not line:
            log("[PROTO] Event stream closed")
            break
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        append_event_log(text)
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            log(f"[PROTO] Failed to decode event: {text}")
            continue
        handle_event(event, aggregator)


async def run_agent() -> None:
    """Main entry point for the persistent Codex bridge."""
    update_status(STATUS_INITIALIZING)
    copy_auth_if_available()
    copy_config_if_available()
    ensure_message_channels()

    aggregator = ResponseAggregator()

    try:
        proc = await launch_codex_process()
    except Exception:
        update_status(STATUS_FAILED)
        return

    tasks = [
        asyncio.create_task(read_event_stream(proc, aggregator)),
        asyncio.create_task(read_stderr(proc)),
        asyncio.create_task(fifo_submission_loop(proc, aggregator)),
    ]

    try:
        return_code = await proc.wait()
        if return_code == 0:
            log("codex proto exited cleanly")
            update_status(STATUS_SHUTTING_DOWN)
        else:
            log(f"codex proto exited with code {return_code}")
            update_status(STATUS_FAILED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        log("Received KeyboardInterrupt; shutting down agent")
