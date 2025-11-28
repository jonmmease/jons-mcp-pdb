"""Stack navigation tools for pdb debugging."""

from typing import Any


def where(session_id: str, limit: int | None = None, offset: int = 0) -> dict[str, Any]:
    """Get current stack trace.

    Args:
        session_id: The session identifier
        limit: Maximum frames to return (optional)
        offset: Number of frames to skip (default: 0)

    Returns:
        Array of stack frames with pagination info
    """
    from ..server import get_client

    client = get_client()
    result = client.send_command(session_id, "where")

    if "error" in result:
        return result

    frames = client._parse_stack_frames(result["output"])
    total_frames = len(frames)

    # Apply pagination
    if limit is not None:
        paginated_frames = frames[offset : offset + limit]
    else:
        paginated_frames = frames[offset:]

    return {
        "frames": [
            {
                "index": frame.index,
                "file": frame.file,
                "line": frame.line,
                "function": frame.function,
                "code": frame.code,
            }
            for frame in paginated_frames
        ],
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total_frames,
            "returned": len(paginated_frames),
        },
    }


def backtrace(
    session_id: str, limit: int | None = None, offset: int = 0
) -> dict[str, Any]:
    """Get current stack trace (alias for where).

    Args:
        session_id: The session identifier
        limit: Maximum frames to return (optional)
        offset: Number of frames to skip (default: 0)

    Returns:
        Array of stack frames with pagination info
    """
    return where(session_id, limit, offset)


def up(session_id: str, count: int = 1) -> dict[str, Any]:
    """Move up in the stack (to caller).

    Args:
        session_id: The session identifier
        count: Number of frames to move (default: 1)

    Returns:
        New current frame information
    """
    from ..server import get_client

    client = get_client()
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


def down(session_id: str, count: int = 1) -> dict[str, Any]:
    """Move down in the stack.

    Args:
        session_id: The session identifier
        count: Number of frames to move (default: 1)

    Returns:
        New current frame information
    """
    from ..server import get_client

    client = get_client()
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
