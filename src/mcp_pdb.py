#!/usr/bin/env python3
"""
FastMCP server that provides Python debugging capabilities through pdb.

This server manages pdb subprocess debugging sessions and exposes pdb features through MCP tools.
Run with: uv run pdb_mcp.py
"""

import subprocess
import sys
import os
import json
import re
import threading
import queue
import time
import signal
import atexit
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
import shutil

from mcp.server.fastmcp import FastMCP

# Configure logging - reduce level to avoid MCP protocol interference
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastMCP server instance
mcp = FastMCP("pdb-mcp")

# Constants
PDB_PROMPT = "(Pdb) "
PDB_PROMPT_PATTERN = re.compile(r"\(Pdb\)\s*$", re.MULTILINE)
BREAKPOINT_SET_PATTERN = re.compile(r"Breakpoint (\d+) at (.+):(\d+)")
CURRENT_LOCATION_PATTERN = re.compile(r"> (.+)\((\d+)\)(.+)\(\)")
STACK_FRAME_PATTERN = re.compile(r"^\s*(.+)\((\d+)\)(.+)\(\)$", re.MULTILINE)
BREAKPOINT_HIT_PATTERN = re.compile(r"Breakpoint (\d+), .+ at (.+):(\d+)")


class DebuggerState(Enum):
    """States of the debugger"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class Config:
    """Configuration for PDB MCP server"""

    python_path: Optional[str] = None
    venv: Optional[str] = None
    working_directory: str = "."
    environment: Dict[str, str] = field(default_factory=dict)
    debug_mode: str = "script"  # "script" or "pytest"
    pytest_args: List[str] = field(default_factory=list)


@dataclass
class Breakpoint:
    """Represents a breakpoint"""

    id: int
    file: str
    line: int
    function: Optional[str] = None
    condition: Optional[str] = None
    temporary: bool = False
    enabled: bool = True
    hit_count: int = 0


@dataclass
class StackFrame:
    """Represents a stack frame"""

    index: int
    file: str
    line: int
    function: str
    code: str


@dataclass
class DebugSession:
    """Represents a debugging session"""

    session_id: str
    process: Optional[subprocess.Popen] = None
    state: DebuggerState = DebuggerState.IDLE
    current_frame: Optional[StackFrame] = None
    breakpoints: Dict[int, Breakpoint] = field(default_factory=dict)
    target_type: str = "script"  # "script", "pytest", "code"
    target: str = ""
    args: List[str] = field(default_factory=list)
    output_queue: queue.Queue = field(default_factory=queue.Queue)
    reader_thread: Optional[threading.Thread] = None
    writer_thread: Optional[threading.Thread] = None
    command_queue: queue.Queue = field(default_factory=queue.Queue)
    last_output: str = ""
    python_executable: str = sys.executable


class PdbClient:
    """Client for managing pdb subprocess sessions"""

    def __init__(self):
        self.sessions: Dict[str, DebugSession] = {}
        self.lock = threading.Lock()
        self.session_counter = 0
        self.config = self._load_config()

    def _load_config(self) -> Config:
        """Load configuration from pdbconfig.json if it exists"""
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
        """Find the appropriate Python executable"""
        # Check config first
        if self.config.python_path:
            return self.config.python_path

        # Check for virtual environment
        venv_paths = []
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

    def _reader_thread(self, session: DebugSession):
        """Thread for reading output from pdb subprocess"""
        try:
            buffer = ""
            while session.process and session.process.poll() is None:
                # Read one character at a time to handle prompts without newlines
                char = session.process.stdout.read(1)
                if not char:
                    continue

                buffer += char

                # If we hit a newline, send the complete line
                if char == "\n":
                    session.output_queue.put(buffer)
                    session.last_output += buffer
                    # logger.debug(f"PDB output: {buffer.rstrip()}")
                    buffer = ""
                # Check if we have a prompt (which may not end with newline)
                elif buffer.endswith(PDB_PROMPT):
                    session.output_queue.put(buffer)
                    session.last_output += buffer
                    # logger.debug(f"PDB prompt detected: {buffer.rstrip()}")
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
        except Exception as e:
            session.state = DebuggerState.ERROR

    def _writer_thread(self, session: DebugSession):
        """Thread for writing commands to pdb subprocess"""
        try:
            while session.process and session.process.poll() is None:
                try:
                    command = session.command_queue.get(timeout=0.1)
                    if command:
                        logger.debug(f"Sending command to PDB: {command}")
                        session.process.stdin.write(command + "\n")
                        session.process.stdin.flush()
                except queue.Empty:
                    continue
        except Exception as e:
            # logger.error(f"Writer thread error: {e}")
            pass

    def _wait_for_prompt(self, session: DebugSession, timeout: float = 5.0) -> bool:
        """Wait for PDB prompt to appear"""
        start_time = time.time()
        accumulated_output = ""
        empty_count = 0

        # First check if we already have a prompt in the last output
        if PDB_PROMPT_PATTERN.search(session.last_output):
            return True

        while time.time() - start_time < timeout:
            try:
                output = session.output_queue.get(timeout=0.1)
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
        return PDB_PROMPT_PATTERN.search(
            accumulated_output
        ) or PDB_PROMPT_PATTERN.search(session.last_output)

    def _read_until_prompt(self, session: DebugSession, timeout: float = 5.0) -> str:
        """Read output until PDB prompt appears"""
        output = ""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                line = session.output_queue.get(timeout=0.1)
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

    def _parse_location(self, output: str) -> Optional[StackFrame]:
        """Parse current location from PDB output"""
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

    def _parse_stack_frames(self, output: str) -> List[StackFrame]:
        """Parse stack frames from 'where' command output"""
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
        """Create a new debugging session"""
        with self.lock:
            self.session_counter += 1
            session_id = f"session_{self.session_counter}"

            session = DebugSession(
                session_id=session_id, python_executable=self._find_python_executable()
            )

            self.sessions[session_id] = session
            return session_id

    def start_debug(
        self, session_id: str, target: str, mode: str = "script", args: List[str] = None
    ) -> Dict[str, Any]:
        """Start debugging a target"""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        if session.process:
            return {"error": "Session already has an active process"}

        # Build command
        if mode == "pytest":
            # For pytest, use pytest with --trace flag to start debugging immediately
            # --trace breaks on every test line, --pdb breaks on failures/errors
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
            if self._wait_for_prompt(session, timeout=10.0):
                return {"status": "started", "session_id": session_id}
            else:
                # Try to get any error output
                error_msg = "Failed to get initial prompt"
                if session.last_output:
                    error_msg += f". Output: {session.last_output[:200]}"
                return {"error": error_msg}

        except Exception as e:
            return {"error": str(e)}

    def send_command(self, session_id: str, command: str) -> Dict[str, Any]:
        """Send a command to the debugger and return output"""
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
        """Close a debugging session"""
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                return False

            # Terminate process if running
            if session.process:
                try:
                    session.process.terminate()
                    session.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    session.process.kill()
                except Exception as e:
                    # logger.error(f"Error terminating process: {e}")
                    pass

            # Remove session
            del self.sessions[session_id]
            return True


# Global PdbClient instance
client = PdbClient()

# Session Management Tools


@mcp.tool()
def start_debug(
    target: str, args: Optional[List[str]] = None, mode: Optional[str] = None
) -> Dict[str, Any]:
    """Initialize a debugging session.

    Args:
        target: Path to script or test file
        args: Command line arguments (optional)
        mode: "script" or "pytest" (optional, defaults to config)

    Returns:
        session_id and status
    """
    session_id = client.create_session()
    mode = mode or client.config.debug_mode

    result = client.start_debug(session_id, target, mode, args)

    if "error" not in result:
        result["session_id"] = session_id

    return result


@mcp.tool()
def stop_debug(session_id: str) -> Dict[str, str]:
    """Terminate the active debugging session.

    Args:
        session_id: The session identifier

    Returns:
        Status of the operation
    """
    success = client.close_session(session_id)

    if success:
        return {"status": "stopped"}
    else:
        return {"status": "error", "message": "Session not found"}


@mcp.tool()
def restart_debug(session_id: str) -> Dict[str, Any]:
    """Restart the current debugging session with same parameters.

    Args:
        session_id: The session identifier

    Returns:
        New session_id and status
    """
    session = client.sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    # Save session info
    target = session.target
    mode = session.target_type
    args = session.args

    # Close old session
    client.close_session(session_id)

    # Start new session
    return start_debug(target, args, mode)


# Breakpoint Management Tools


@mcp.tool()
def set_breakpoint(
    session_id: str,
    file: str,
    line: Optional[int] = None,
    function: Optional[str] = None,
    condition: Optional[str] = None,
    temporary: bool = False,
) -> Dict[str, Any]:
    """Set a breakpoint at specified location.

    Args:
        session_id: The session identifier
        file: File path (absolute or relative)
        line: Line number (optional if function specified)
        function: Function name (optional if line specified)
        condition: Conditional expression (optional)
        temporary: One-time breakpoint (default: false)

    Returns:
        breakpoint_id and location
    """
    if not line and not function:
        return {"error": "Either line or function must be specified"}

    # Build break command
    cmd = "tbreak" if temporary else "break"

    if function:
        cmd += f" {function}"
    else:
        cmd += f" {file}:{line}"

    if condition:
        cmd += f", {condition}"

    result = client.send_command(session_id, cmd)

    if "error" in result:
        return result

    # Parse breakpoint ID from output
    match = BREAKPOINT_SET_PATTERN.search(result["output"])
    if match:
        bp_id = int(match.group(1))
        resolved_file = match.group(2)
        resolved_line = int(match.group(3))

        # Store breakpoint info
        session = client.sessions.get(session_id)
        if session:
            bp = Breakpoint(
                id=bp_id,
                file=resolved_file,
                line=resolved_line,
                function=function,
                condition=condition,
                temporary=temporary,
            )
            session.breakpoints[bp_id] = bp

        return {
            "breakpoint_id": bp_id,
            "location": {"file": resolved_file, "line": resolved_line},
        }

    return {"error": "Failed to set breakpoint"}


@mcp.tool()
def remove_breakpoint(session_id: str, breakpoint_id: int) -> Dict[str, str]:
    """Remove a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        Status of the operation
    """
    result = client.send_command(session_id, f"clear {breakpoint_id}")

    if "error" not in result:
        session = client.sessions.get(session_id)
        if session and breakpoint_id in session.breakpoints:
            del session.breakpoints[breakpoint_id]
        return {"status": "removed"}

    return {"status": "error", "message": result.get("error", "Unknown error")}


@mcp.tool()
def list_breakpoints(session_id: str) -> Dict[str, Any]:
    """List all breakpoints.

    Args:
        session_id: The session identifier

    Returns:
        Array of breakpoint objects
    """
    result = client.send_command(session_id, "break")

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    # Return stored breakpoint info
    breakpoints = []
    for bp in session.breakpoints.values():
        breakpoints.append(
            {
                "id": bp.id,
                "file": bp.file,
                "line": bp.line,
                "function": bp.function,
                "condition": bp.condition,
                "enabled": bp.enabled,
                "hit_count": bp.hit_count,
            }
        )

    return {"breakpoints": breakpoints}


@mcp.tool()
def enable_breakpoint(session_id: str, breakpoint_id: int) -> Dict[str, Any]:
    """Enable a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        New enabled state
    """
    result = client.send_command(session_id, f"enable {breakpoint_id}")

    if "error" not in result:
        session = client.sessions.get(session_id)
        if session and breakpoint_id in session.breakpoints:
            session.breakpoints[breakpoint_id].enabled = True
        return {"status": True}

    return {"error": result.get("error", "Failed to enable breakpoint")}


@mcp.tool()
def disable_breakpoint(session_id: str, breakpoint_id: int) -> Dict[str, Any]:
    """Disable a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        New enabled state
    """
    result = client.send_command(session_id, f"disable {breakpoint_id}")

    if "error" not in result:
        session = client.sessions.get(session_id)
        if session and breakpoint_id in session.breakpoints:
            session.breakpoints[breakpoint_id].enabled = False
        return {"status": False}

    return {"error": result.get("error", "Failed to disable breakpoint")}


# Execution Control Tools


@mcp.tool()
def continue_execution(session_id: str) -> Dict[str, Any]:
    """Continue execution until next breakpoint.

    Args:
        session_id: The session identifier

    Returns:
        Location where execution stopped and reason
    """
    session = client.sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    session.state = DebuggerState.RUNNING
    result = client.send_command(session_id, "continue")

    if "error" in result:
        return result

    # Parse output to determine stop reason
    output = result["output"]
    # Check for state changes
    location = session.current_frame
    reason = "unknown"

    if "Breakpoint" in output:
        reason = "breakpoint"
        # Update hit count
        match = BREAKPOINT_HIT_PATTERN.search(output)
        if match:
            bp_id = int(match.group(1))
            if bp_id in session.breakpoints:
                session.breakpoints[bp_id].hit_count += 1
    elif "--Return--" in output:
        reason = "return"
    elif "Exception" in output:
        reason = "exception"
    elif "The program finished" in output or "exited normally" in output:
        reason = "end"
        session.state = DebuggerState.FINISHED

    return {
        "stopped_at": {
            "file": location.file if location else None,
            "line": location.line if location else None,
            "function": location.function if location else None,
        },
        "reason": reason,
    }


@mcp.tool()
def step(session_id: str) -> Dict[str, Any]:
    """Step into function calls (execute next line).

    Args:
        session_id: The session identifier

    Returns:
        New execution position
    """
    result = client.send_command(session_id, "step")

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    location = session.current_frame if session else None

    response = {
        "location": {
            "file": location.file if location else None,
            "line": location.line if location else None,
            "function": location.function if location else None,
        }
    }

    # Check if we entered a function
    if "call" in result["output"].lower():
        response["entered_function"] = location.function if location else None

    return response


@mcp.tool()
def next(session_id: str) -> Dict[str, Any]:
    """Step over function calls (execute next line in current function).

    Args:
        session_id: The session identifier

    Returns:
        New execution position
    """
    result = client.send_command(session_id, "next")

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    location = session.current_frame if session else None

    return {
        "location": {
            "file": location.file if location else None,
            "line": location.line if location else None,
            "function": location.function if location else None,
        }
    }


@mcp.tool()
def return_from_function(session_id: str) -> Dict[str, Any]:
    """Continue until current function returns.

    Args:
        session_id: The session identifier

    Returns:
        Return point and value
    """
    result = client.send_command(session_id, "return")

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    location = session.current_frame if session else None

    response = {
        "location": {
            "file": location.file if location else None,
            "line": location.line if location else None,
            "function": location.function if location else None,
        }
    }

    # Try to extract return value from output
    if "--Return--" in result["output"]:
        lines = result["output"].split("\n")
        for line in lines:
            if "--Return--" in line:
                response["return_value"] = line.split("--Return--")[1].strip()
                break

    return response


@mcp.tool()
def until(session_id: str, line: int) -> Dict[str, Any]:
    """Continue until specified line.

    Args:
        session_id: The session identifier
        line: Target line number in current file

    Returns:
        Location where execution stopped
    """
    result = client.send_command(session_id, f"until {line}")

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    location = session.current_frame if session else None

    return {
        "location": {
            "file": location.file if location else None,
            "line": location.line if location else None,
            "function": location.function if location else None,
        }
    }


# Stack Navigation Tools


@mcp.tool()
def where(session_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """Get current stack trace.

    Args:
        session_id: The session identifier
        limit: Maximum frames to return (optional)

    Returns:
        Array of stack frames
    """
    result = client.send_command(session_id, "where")

    if "error" in result:
        return result

    frames = client._parse_stack_frames(result["output"])

    if limit and len(frames) > limit:
        frames = frames[:limit]

    return {
        "frames": [
            {
                "index": frame.index,
                "file": frame.file,
                "line": frame.line,
                "function": frame.function,
                "code": frame.code,
            }
            for frame in frames
        ]
    }


# Alias for where
backtrace = where


@mcp.tool()
def up(session_id: str, count: int = 1) -> Dict[str, Any]:
    """Move up in the stack (to caller).

    Args:
        session_id: The session identifier
        count: Number of frames to move (default: 1)

    Returns:
        New current frame information
    """
    cmd = "up" if count == 1 else f"up {count}"
    result = client.send_command(session_id, cmd)

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    location = session.current_frame if session else None

    return {
        "frame": {
            "file": location.file if location else None,
            "line": location.line if location else None,
            "function": location.function if location else None,
        }
    }


@mcp.tool()
def down(session_id: str, count: int = 1) -> Dict[str, Any]:
    """Move down in the stack.

    Args:
        session_id: The session identifier
        count: Number of frames to move (default: 1)

    Returns:
        New current frame information
    """
    cmd = "down" if count == 1 else f"down {count}"
    result = client.send_command(session_id, cmd)

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    location = session.current_frame if session else None

    return {
        "frame": {
            "file": location.file if location else None,
            "line": location.line if location else None,
            "function": location.function if location else None,
        }
    }


# Inspection Tools


@mcp.tool()
def list_source(
    session_id: str, line: Optional[int] = None, range: int = 5
) -> Dict[str, Any]:
    """Show source code around current or specified position.

    Args:
        session_id: The session identifier
        line: Center line (optional, defaults to current)
        range: Number of lines before/after (default: 5)

    Returns:
        Source code lines with line numbers and current line
    """
    if line:
        cmd = f"list {line - range}, {line + range}"
    else:
        cmd = "list"

    result = client.send_command(session_id, cmd)

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    current_line = (
        session.current_frame.line if session and session.current_frame else None
    )

    return {"source": result["output"], "current_line": current_line}


@mcp.tool()
def inspect_variable(
    session_id: str, name: str, frame: Optional[int] = None
) -> Dict[str, Any]:
    """Get detailed information about a variable.

    Args:
        session_id: The session identifier
        name: Variable name
        frame: Stack frame index (optional, defaults to current)

    Returns:
        Variable details including value, type, and attributes
    """
    # Switch frame if needed
    if frame is not None:
        result = client.send_command(session_id, f"up {frame}")
        if "error" in result:
            return result

    # Get variable info
    result = client.send_command(session_id, f"p {name}")
    if "error" in result:
        return result

    value = result["output"].replace(PDB_PROMPT, "").strip()

    # Get type
    type_result = client.send_command(session_id, f"p type({name}).__name__")
    type_name = type_result["output"].replace(PDB_PROMPT, "").strip().strip("'\"")

    # Get repr
    repr_result = client.send_command(session_id, f"p repr({name})")
    repr_value = repr_result["output"].replace(PDB_PROMPT, "").strip()

    # Get attributes for complex types
    attributes = {}
    if type_name not in ["int", "float", "str", "bool", "NoneType"]:
        attrs_result = client.send_command(session_id, f"p dir({name})")
        if "error" not in attrs_result:
            try:
                attrs_str = attrs_result["output"].replace(PDB_PROMPT, "").strip()
                attr_list = eval(attrs_str)
                for attr in attr_list:
                    if not attr.startswith("_"):
                        attr_result = client.send_command(
                            session_id, f"p {name}.{attr}"
                        )
                        if "error" not in attr_result:
                            attributes[attr] = (
                                attr_result["output"].replace(PDB_PROMPT, "").strip()
                            )
            except:
                pass

    # Switch back frame if needed
    if frame is not None:
        client.send_command(session_id, f"down {frame}")

    return {
        "name": name,
        "value": value,
        "type": type_name,
        "attributes": attributes,
        "repr": repr_value,
        "str": value,
    }


@mcp.tool()
def list_variables(
    session_id: str, frame: Optional[int] = None, include_globals: bool = False
) -> Dict[str, Any]:
    """List all variables in current scope.

    Args:
        session_id: The session identifier
        frame: Stack frame index (optional)
        include_globals: Include global variables (default: false)

    Returns:
        Local and global variables
    """
    # Switch frame if needed
    if frame is not None:
        result = client.send_command(session_id, f"up {frame}")
        if "error" in result:
            return result

    # Get locals
    locals_result = client.send_command(session_id, "p locals()")
    if "error" in locals_result:
        return locals_result

    locals_dict = {}
    try:
        locals_str = locals_result["output"].replace(PDB_PROMPT, "").strip()
        locals_raw = eval(locals_str)
        for k, v in locals_raw.items():
            locals_dict[k] = repr(v)[:100]  # Truncate long values
    except:
        pass

    result = {"locals": locals_dict}

    # Get globals if requested
    if include_globals:
        globals_result = client.send_command(session_id, "p globals()")
        if "error" not in globals_result:
            globals_dict = {}
            try:
                globals_str = globals_result["output"].replace(PDB_PROMPT, "").strip()
                globals_raw = eval(globals_str)
                for k, v in globals_raw.items():
                    if not k.startswith("__"):  # Skip dunder variables
                        globals_dict[k] = repr(v)[:100]
            except:
                pass
            result["globals"] = globals_dict

    # Switch back frame if needed
    if frame is not None:
        client.send_command(session_id, f"down {frame}")

    return result


@mcp.tool()
def evaluate(
    session_id: str, expression: str, frame: Optional[int] = None
) -> Dict[str, Any]:
    """Evaluate an expression in the current context.

    Args:
        session_id: The session identifier
        expression: Python expression
        frame: Stack frame index (optional)

    Returns:
        Evaluation result
    """
    # Switch frame if needed
    if frame is not None:
        result = client.send_command(session_id, f"up {frame}")
        if "error" in result:
            return result

    # Evaluate expression
    result = client.send_command(session_id, f"p {expression}")

    # Switch back frame if needed
    if frame is not None:
        client.send_command(session_id, f"down {frame}")

    if "error" in result:
        return result

    value = result["output"].replace(PDB_PROMPT, "").strip()

    # Get type
    type_result = client.send_command(session_id, f"p type({expression}).__name__")
    type_name = "unknown"
    if "error" not in type_result:
        type_name = type_result["output"].replace(PDB_PROMPT, "").strip().strip("'\"")

    # Check for exceptions
    if "Traceback" in value or "Error" in value:
        return {"result": value, "type": "error", "error": value}

    return {"result": value, "type": type_name}


# Cleanup and main


def cleanup():
    """Ensure all debugging sessions are closed when the MCP server exits."""
    # logger.info("Running cleanup...")
    for session_id in list(client.sessions.keys()):
        try:
            client.close_session(session_id)
        except Exception as e:
            # logger.error(f"Error closing session {session_id}: {e}")
            pass
    # logger.info("Cleanup complete")


# Register cleanup handler
atexit.register(cleanup)


def main():
    """Initialize and run the FastMCP server."""
    # MCP servers should not output to stderr during normal startup
    # as it's treated as an error by the MCP client

    # Handle signals gracefully
    def signal_handler(sig, frame):
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Run the server
        mcp.run()
    except Exception as e:
        # Log any startup errors to stderr (will help debug transport issues)
        import traceback
        print(f"MCP server error: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
