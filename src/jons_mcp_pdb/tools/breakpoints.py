"""Breakpoint management tools for pdb debugging."""

from typing import Any

from ..constants import BREAKPOINT_SET_PATTERN
from ..pdb_client import Breakpoint


def set_breakpoint(
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
    from ..server import get_client

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

    client = get_client()
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


def remove_breakpoint(session_id: str, breakpoint_id: int) -> dict[str, str]:
    """Remove a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        Status of the operation
    """
    from ..server import get_client

    client = get_client()
    result = client.send_command(session_id, f"clear {breakpoint_id}")

    if "error" not in result:
        session = client.sessions.get(session_id)
        if session and breakpoint_id in session.breakpoints:
            del session.breakpoints[breakpoint_id]
        return {"status": "removed"}

    return {"status": "error", "message": result.get("error", "Unknown error")}


def list_breakpoints(
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
    from ..server import get_client

    client = get_client()
    result = client.send_command(session_id, "break")

    if "error" in result:
        return result

    session = client.sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    # Get all breakpoints
    all_breakpoints: list[dict[str, Any]] = []
    for bp in session.breakpoints.values():
        all_breakpoints.append(
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

    # Sort by ID for consistent ordering
    all_breakpoints.sort(key=lambda x: x["id"])
    total_breakpoints = len(all_breakpoints)

    # Apply pagination
    if limit is not None:
        paginated_breakpoints = all_breakpoints[offset : offset + limit]
    else:
        paginated_breakpoints = all_breakpoints[offset:]

    return {
        "breakpoints": paginated_breakpoints,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total_breakpoints,
            "returned": len(paginated_breakpoints),
        },
    }


def enable_breakpoint(session_id: str, breakpoint_id: int) -> dict[str, Any]:
    """Enable a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        New enabled state
    """
    from ..server import get_client

    client = get_client()
    result = client.send_command(session_id, f"enable {breakpoint_id}")

    if "error" not in result:
        session = client.sessions.get(session_id)
        if session and breakpoint_id in session.breakpoints:
            session.breakpoints[breakpoint_id].enabled = True
        return {"status": True}

    return {"error": result.get("error", "Failed to enable breakpoint")}


def disable_breakpoint(session_id: str, breakpoint_id: int) -> dict[str, Any]:
    """Disable a breakpoint.

    Args:
        session_id: The session identifier
        breakpoint_id: Breakpoint identifier

    Returns:
        New enabled state
    """
    from ..server import get_client

    client = get_client()
    result = client.send_command(session_id, f"disable {breakpoint_id}")

    if "error" not in result:
        session = client.sessions.get(session_id)
        if session and breakpoint_id in session.breakpoints:
            session.breakpoints[breakpoint_id].enabled = False
        return {"status": False}

    return {"error": result.get("error", "Failed to disable breakpoint")}
