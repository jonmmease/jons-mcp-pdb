"""PDB client for managing pdb subprocess sessions."""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_TIMEOUT,
    PDB_PROMPT,
    PDB_PROMPT_PATTERN,
    PROCESS_TERMINATE_TIMEOUT,
    QUEUE_TIMEOUT,
    STARTUP_TIMEOUT,
    DebuggerState,
)

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Configuration for PDB MCP server."""

    python_path: str | None = None
    venv: str | None = None
    working_directory: str = "."
    environment: dict[str, str] = field(default_factory=dict)
    pytest_args: list[str] = field(default_factory=list)


@dataclass
class Breakpoint:
    """Represents a breakpoint."""

    id: int
    file: str
    line: int
    function: str | None = None
    condition: str | None = None
    temporary: bool = False
    enabled: bool = True
    hit_count: int = 0


@dataclass
class StackFrame:
    """Represents a stack frame."""

    index: int
    file: str
    line: int
    function: str
    code: str


@dataclass
class DebugSession:
    """Represents a debugging session."""

    session_id: str
    process: subprocess.Popen[str] | None = None
    state: DebuggerState = DebuggerState.IDLE
    current_frame: StackFrame | None = None
    breakpoints: dict[int, Breakpoint] = field(default_factory=dict)
    target_type: str = "script"  # "script", "pytest", "code"
    target: str = ""
    args: list[str] = field(default_factory=list)
    output_queue: queue.Queue[str] = field(default_factory=queue.Queue)
    reader_thread: threading.Thread | None = None
    writer_thread: threading.Thread | None = None
    command_queue: queue.Queue[str] = field(default_factory=queue.Queue)
    last_output: str = ""
    python_executable: str = field(default_factory=lambda: sys.executable)


class PdbClient:
    """Client for managing pdb subprocess sessions."""

    def __init__(self) -> None:
        self.sessions: dict[str, DebugSession] = {}
        self.lock = threading.Lock()
        self.session_counter = 0
        self.config = self._load_config()

    def _load_config(self) -> Config:
        """Load configuration from pdbconfig.json if it exists."""
        config_path = Path("pdbconfig.json")
        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                return Config(**data)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return Config()

    def _find_python_executable(self) -> str:
        """Find the appropriate Python executable."""
        # Check config first
        if self.config.python_path:
            return self.config.python_path

        # Check for virtual environment
        venv_paths: list[Path] = []
        if self.config.venv:
            venv_paths.append(Path(self.config.venv))

        # Common virtual environment locations
        venv_paths.extend(
            [
                Path(".venv"),
                Path("venv"),
                Path(".pixi/envs/default"),
            ]
        )

        for venv_path in venv_paths:
            if venv_path.exists():
                # Check for Python executable
                if sys.platform == "win32":
                    python_exe = venv_path / "Scripts" / "python.exe"
                else:
                    python_exe = venv_path / "bin" / "python"

                if python_exe.exists():
                    return str(python_exe)

        # Fall back to system Python
        return sys.executable

    def _reader_thread(self, session: DebugSession) -> None:
        """Thread for reading output from pdb subprocess."""
        try:
            buffer = ""
            while session.process and session.process.poll() is None:
                # Read one character at a time to handle prompts without newlines
                if session.process.stdout is None:
                    break
                char = session.process.stdout.read(1)
                if not char:
                    continue

                buffer += char

                # If we hit a newline, send the complete line
                if char == "\n":
                    session.output_queue.put(buffer)
                    session.last_output += buffer
                    buffer = ""
                # Check if we have a prompt (which may not end with newline)
                elif buffer.endswith(PDB_PROMPT):
                    session.output_queue.put(buffer)
                    session.last_output += buffer
                    session.state = DebuggerState.PAUSED
                    buffer = ""

                # Check for state changes in complete lines
                if (
                    "--Return--" in session.last_output
                    or "The program finished" in session.last_output
                ):
                    session.state = DebuggerState.FINISHED

            # Send any remaining buffer content
            if buffer:
                session.output_queue.put(buffer)
                session.last_output += buffer
        except Exception:
            session.state = DebuggerState.ERROR

    def _writer_thread(self, session: DebugSession) -> None:
        """Thread for writing commands to pdb subprocess."""
        try:
            while session.process and session.process.poll() is None:
                try:
                    command = session.command_queue.get(timeout=QUEUE_TIMEOUT)
                    if command and session.process.stdin:
                        logger.debug(f"Sending command to PDB: {command}")
                        session.process.stdin.write(command + "\n")
                        session.process.stdin.flush()
                except queue.Empty:
                    continue
        except Exception:
            pass

    def _wait_for_prompt(
        self, session: DebugSession, timeout: float = DEFAULT_TIMEOUT
    ) -> bool:
        """Wait for PDB prompt to appear."""
        start_time = time.time()
        accumulated_output = ""
        empty_count = 0

        # First check if we already have a prompt in the last output
        if PDB_PROMPT_PATTERN.search(session.last_output):
            return True

        while time.time() - start_time < timeout:
            try:
                output = session.output_queue.get(timeout=QUEUE_TIMEOUT)
                accumulated_output += output
                session.last_output += output
                empty_count = 0  # Reset empty count on successful read

                # Check for prompt using regex to handle various formats
                if PDB_PROMPT_PATTERN.search(accumulated_output):
                    return True
            except queue.Empty:
                empty_count += 1
                # Give it more chances before checking - prompt might be coming
                if empty_count < 3:
                    continue

                # Check accumulated output after multiple empty reads
                if PDB_PROMPT_PATTERN.search(
                    accumulated_output
                ) or PDB_PROMPT_PATTERN.search(session.last_output):
                    return True
                continue

        # Final check before giving up
        return bool(
            PDB_PROMPT_PATTERN.search(accumulated_output)
            or PDB_PROMPT_PATTERN.search(session.last_output)
        )

    def _read_until_prompt(
        self, session: DebugSession, timeout: float = DEFAULT_TIMEOUT
    ) -> str:
        """Read output until PDB prompt appears."""
        output = ""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                line = session.output_queue.get(timeout=QUEUE_TIMEOUT)
                output += line

                # Check for prompt using regex
                if PDB_PROMPT_PATTERN.search(output):
                    break
            except queue.Empty:
                # Final check of accumulated output
                if PDB_PROMPT_PATTERN.search(output):
                    break
                continue

        return output

    def _parse_location(self, output: str) -> StackFrame | None:
        """Parse current location from PDB output."""
        from .constants import CURRENT_LOCATION_PATTERN

        match = CURRENT_LOCATION_PATTERN.search(output)
        if match:
            return StackFrame(
                index=0,
                file=match.group(1),
                line=int(match.group(2)),
                function=match.group(3).strip(),
                code="",
            )
        return None

    def _parse_stack_frames(self, output: str) -> list[StackFrame]:
        """Parse stack frames from 'where' command output."""
        from .constants import STACK_FRAME_PATTERN

        frames = []
        lines = output.split("\n")

        for i, line in enumerate(lines):
            match = STACK_FRAME_PATTERN.match(line)
            if match:
                frames.append(
                    StackFrame(
                        index=i,
                        file=match.group(1).strip(),
                        line=int(match.group(2)),
                        function=match.group(3).strip(),
                        code="",
                    )
                )

        return frames

    def create_session(self) -> str:
        """Create a new debugging session."""
        with self.lock:
            self.session_counter += 1
            session_id = f"session_{self.session_counter}"

            session = DebugSession(
                session_id=session_id, python_executable=self._find_python_executable()
            )

            self.sessions[session_id] = session
            return session_id

    def start_debug(
        self,
        session_id: str,
        target: str,
        mode: str = "script",
        args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Start debugging a target."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        if session.process:
            return {"error": "Session already has an active process"}

        # Build command
        if mode == "pytest":
            # For pytest, use pytest with --trace flag to start debugging immediately
            cmd = [session.python_executable, "-m", "pytest", "--trace", "-s", "-v"]

            # Add pytest-specific configuration
            if self.config.pytest_args:
                cmd.extend(self.config.pytest_args)

            # Add target (test file/directory)
            cmd.append(target)

            # Add any additional args
            if args:
                cmd.extend(args)
        else:
            # Standard pdb mode for regular scripts
            cmd = [session.python_executable, "-m", "pdb", target]
            if args:
                cmd.extend(args)

        # Set up environment
        env = os.environ.copy()
        env.update(self.config.environment)

        # Start process
        try:
            session.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,  # Unbuffered for immediate output
                cwd=self.config.working_directory,
                env=env,
            )

            session.target = target
            session.target_type = mode
            session.args = args or []
            session.state = DebuggerState.PAUSED

            # Start reader and writer threads
            session.reader_thread = threading.Thread(
                target=self._reader_thread, args=(session,), daemon=True
            )
            session.writer_thread = threading.Thread(
                target=self._writer_thread, args=(session,), daemon=True
            )

            session.reader_thread.start()
            session.writer_thread.start()

            # Wait for initial prompt with longer timeout for slow starts
            if self._wait_for_prompt(session, timeout=STARTUP_TIMEOUT):
                return {"status": "started", "session_id": session_id}
            else:
                # Try to get any error output
                error_msg = "Failed to get initial prompt"
                if session.last_output:
                    error_msg += f". Output: {session.last_output[:200]}"
                return {"error": error_msg}

        except Exception as e:
            return {"error": str(e)}

    def send_command(self, session_id: str, command: str) -> dict[str, Any]:
        """Send a command to the debugger and return output."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        if not session.process or session.process.poll() is not None:
            return {"error": "No active process"}

        # Clear output queue
        while not session.output_queue.empty():
            try:
                session.output_queue.get_nowait()
            except queue.Empty:
                break

        # Send command
        session.command_queue.put(command)

        # Read response
        output = self._read_until_prompt(session)

        # Update current location if needed
        location = self._parse_location(output)
        if location:
            session.current_frame = location

        return {"output": output, "state": session.state.value}

    def close_session(self, session_id: str) -> bool:
        """Close a debugging session."""
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return False

            # Terminate process if running
            if session.process:
                try:
                    session.process.terminate()
                    session.process.wait(timeout=PROCESS_TERMINATE_TIMEOUT)
                except subprocess.TimeoutExpired:
                    session.process.kill()
                except Exception:
                    pass

            # Remove session
            del self.sessions[session_id]
            return True
