"""Execution control tools for pdb debugging."""

from typing import Any

from ..constants import BREAKPOINT_HIT_PATTERN, DebuggerState


def continue_execution(session_id: str) -> dict[str, Any]:
    """Continue execution until next breakpoint.

    Args:
        session_id: The session identifier

    Returns:
        Location where execution stopped and reason
    """
    from ..server import get_client

    client = get_client()
    session = client.sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    session.state = DebuggerState.RUNNING
    result = client.send_command(session_id, "continue")

    if "error" in result:
        return result

    # Parse output to determine stop reason
    output = result["output"]
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


def step(session_id: str) -> dict[str, Any]:
    """Step into function calls (execute next line).

    Args:
        session_id: The session identifier

    Returns:
        New execution position
    """
    from ..server import get_client

    client = get_client()
    result = client.send_command(session_id, "step")

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    location = session.current_frame if session else None

    response: dict[str, Any] = {
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


def next_line(session_id: str) -> dict[str, Any]:
    """Step over function calls (execute next line in current function).

    Args:
        session_id: The session identifier

    Returns:
        New execution position
    """
    from ..server import get_client

    client = get_client()
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


def return_from_function(session_id: str) -> dict[str, Any]:
    """Continue until current function returns.

    Args:
        session_id: The session identifier

    Returns:
        Return point and value
    """
    from ..server import get_client

    client = get_client()
    result = client.send_command(session_id, "return")

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    location = session.current_frame if session else None

    response: dict[str, Any] = {
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


def until(session_id: str, line: int) -> dict[str, Any]:
    """Continue until specified line.

    Args:
        session_id: The session identifier
        line: Target line number in current file

    Returns:
        Location where execution stopped
    """
    from ..server import get_client

    client = get_client()
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
