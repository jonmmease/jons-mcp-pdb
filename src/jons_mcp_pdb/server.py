"""FastMCP server setup and lifespan management for pdb debugging."""

from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from .pdb_client import PdbClient
from .tools import (
    continue_execution,
    disable_breakpoint,
    down,
    enable_breakpoint,
    evaluate,
    inspect_variable,
    list_breakpoints,
    list_source,
    list_variables,
    next_line,
    remove_breakpoint,
    restart_debug,
    return_from_function,
    set_breakpoint,
    start_debug,
    step,
    stop_debug,
    until,
    up,
    where,
)

# Configure logging - reduce level to avoid MCP protocol interference
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global PdbClient instance
_client: PdbClient | None = None


def get_client() -> PdbClient:
    """Get the global PdbClient instance."""
    global _client
    if _client is None:
        _client = PdbClient()
    return _client


def cleanup() -> None:
    """Ensure all debugging sessions are closed when the MCP server exits."""
    global _client
    if _client is not None:
        for session_id in list(_client.sessions.keys()):
            try:
                _client.close_session(session_id)
            except Exception:
                pass


# Register cleanup handler
atexit.register(cleanup)


@asynccontextmanager
async def lifespan(mcp: FastMCP) -> AsyncIterator[None]:
    """Manage PdbClient lifecycle."""
    global _client
    _client = PdbClient()
    logger.info("PDB MCP server started")

    yield

    # Cleanup on shutdown
    cleanup()
    logger.info("PDB MCP server stopped")


# Create FastMCP server instance
mcp = FastMCP(
    "pdb-mcp",
    lifespan=lifespan,
    instructions="""Python debugger (pdb) MCP server providing debugging capabilities.

Available tool categories:
- Session management: start_debug, stop_debug, restart_debug
- Breakpoint management: set_breakpoint, remove_breakpoint, list_breakpoints, enable_breakpoint, disable_breakpoint
- Execution control: continue_execution, step, next, return_from_function, until
- Stack navigation: where, backtrace, up, down
- Inspection: list_source, inspect_variable, list_variables, evaluate

All list operations support pagination via limit and offset parameters.""",
)


# Register all tools with the MCP server
@mcp.tool()
def mcp_start_debug(
    target: str, mode: str, args: list[str] | None = None
) -> dict[str, Any]:
    """Initialize a debugging session.

    Args:
        target: Path to script or test file
        mode: "script" or "pytest"
        args: Command line arguments (optional)

    Returns:
        session_id and status
    """
    return start_debug(target, mode, args)


@mcp.tool()
def mcp_stop_debug(session_id: str) -> dict[str, str]:
    """Terminate the active debugging session.

    Args:
        session_id: The session identifier

    Returns:
        Status of the operation
    """
    return stop_debug(session_id)


@mcp.tool()
def mcp_restart_debug(session_id: str) -> dict[str, Any]:
    """Restart the current debugging session with same parameters.

    Args:
        session_id: The session identifier

    Returns:
        New session_id and status
    """
    return restart_debug(session_id)


@mcp.tool()
def mcp_set_breakpoint(
    session_id: str,
    file: str,
    line: int | None = None,
    function: str | None = None,
    condition: str | None = None,
    temporary: bool = False,
) -> dict[str, Any]:
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
    return set_breakpoint(session_id, file, line, function, condition, temporary)


@mcp.tool()
def mcp_remove_breakpoint(session_id: str, breakpoint_id: int) -> dict[str, str]:
    """Remove a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        Status of the operation
    """
    return remove_breakpoint(session_id, breakpoint_id)


@mcp.tool()
def mcp_list_breakpoints(
    session_id: str, limit: int | None = None, offset: int = 0
) -> dict[str, Any]:
    """List all breakpoints.

    Args:
        session_id: The session identifier
        limit: Maximum number of breakpoints to return (optional)
        offset: Number of breakpoints to skip (default: 0)

    Returns:
        Array of breakpoint objects with pagination info
    """
    return list_breakpoints(session_id, limit, offset)


@mcp.tool()
def mcp_enable_breakpoint(session_id: str, breakpoint_id: int) -> dict[str, Any]:
    """Enable a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        New enabled state
    """
    return enable_breakpoint(session_id, breakpoint_id)


@mcp.tool()
def mcp_disable_breakpoint(session_id: str, breakpoint_id: int) -> dict[str, Any]:
    """Disable a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        New enabled state
    """
    return disable_breakpoint(session_id, breakpoint_id)


@mcp.tool()
def mcp_continue_execution(session_id: str) -> dict[str, Any]:
    """Continue execution until next breakpoint.

    Args:
        session_id: The session identifier

    Returns:
        Location where execution stopped and reason
    """
    return continue_execution(session_id)


@mcp.tool()
def mcp_step(session_id: str) -> dict[str, Any]:
    """Step into function calls (execute next line).

    Args:
        session_id: The session identifier

    Returns:
        New execution position
    """
    return step(session_id)


@mcp.tool()
def mcp_next(session_id: str) -> dict[str, Any]:
    """Step over function calls (execute next line in current function).

    Args:
        session_id: The session identifier

    Returns:
        New execution position
    """
    return next_line(session_id)


@mcp.tool()
def mcp_return_from_function(session_id: str) -> dict[str, Any]:
    """Continue until current function returns.

    Args:
        session_id: The session identifier

    Returns:
        Return point and value
    """
    return return_from_function(session_id)


@mcp.tool()
def mcp_until(session_id: str, line: int) -> dict[str, Any]:
    """Continue until specified line.

    Args:
        session_id: The session identifier
        line: Target line number in current file

    Returns:
        Location where execution stopped
    """
    return until(session_id, line)


@mcp.tool()
def mcp_where(
    session_id: str, limit: int | None = None, offset: int = 0
) -> dict[str, Any]:
    """Get current stack trace.

    Args:
        session_id: The session identifier
        limit: Maximum frames to return (optional)
        offset: Number of frames to skip (default: 0)

    Returns:
        Array of stack frames with pagination info
    """
    return where(session_id, limit, offset)


@mcp.tool()
def mcp_up(session_id: str, count: int = 1) -> dict[str, Any]:
    """Move up in the stack (to caller).

    Args:
        session_id: The session identifier
        count: Number of frames to move (default: 1)

    Returns:
        New current frame information
    """
    return up(session_id, count)


@mcp.tool()
def mcp_down(session_id: str, count: int = 1) -> dict[str, Any]:
    """Move down in the stack.

    Args:
        session_id: The session identifier
        count: Number of frames to move (default: 1)

    Returns:
        New current frame information
    """
    return down(session_id, count)


@mcp.tool()
def mcp_list_source(
    session_id: str,
    line: int | None = None,
    range: int = 5,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Show source code around current or specified position.

    Args:
        session_id: The session identifier
        line: Center line (optional, defaults to current)
        range: Number of lines before/after (default: 5)
        limit: Maximum number of lines to return (optional)
        offset: Number of lines to skip from the start (default: 0)

    Returns:
        Source code lines with line numbers, current line, and pagination info
    """
    return list_source(session_id, line, range, limit, offset)


@mcp.tool()
def mcp_inspect_variable(
    session_id: str,
    name: str,
    frame: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Get detailed information about a variable.

    Args:
        session_id: The session identifier
        name: Variable name
        frame: Stack frame index (optional, defaults to current)
        limit: Maximum number of attributes to return (optional)
        offset: Number of attributes to skip (default: 0)

    Returns:
        Variable details including value, type, and attributes with pagination info
    """
    return inspect_variable(session_id, name, frame, limit, offset)


@mcp.tool()
def mcp_list_variables(
    session_id: str,
    frame: int | None = None,
    include_globals: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """List all variables in current scope.

    Args:
        session_id: The session identifier
        frame: Stack frame index (optional)
        include_globals: Include global variables (default: false)
        limit: Maximum number of variables to return per category (optional)
        offset: Number of variables to skip per category (default: 0)

    Returns:
        Local and global variables with pagination info
    """
    return list_variables(session_id, frame, include_globals, limit, offset)


@mcp.tool()
def mcp_evaluate(
    session_id: str, expression: str, frame: int | None = None
) -> dict[str, Any]:
    """Evaluate an expression in the current context.

    Args:
        session_id: The session identifier
        expression: Python expression
        frame: Stack frame index (optional)

    Returns:
        Evaluation result
    """
    return evaluate(session_id, expression, frame)


def main() -> None:
    """Initialize and run the FastMCP server."""

    # Handle signals gracefully
    def signal_handler(sig: int, frame: Any) -> None:
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Run the server
        mcp.run()
    except Exception as e:
        # Log any startup errors to stderr
        import traceback

        print(f"MCP server error: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
