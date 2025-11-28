"""Session management tools for pdb debugging."""

from typing import Any


def start_debug(
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
    from ..server import get_client

    client = get_client()
    session_id = client.create_session()

    result = client.start_debug(session_id, target, mode, args)

    if "error" not in result:
        result["session_id"] = session_id

    return result


def stop_debug(session_id: str) -> dict[str, str]:
    """Terminate the active debugging session.

    Args:
        session_id: The session identifier

    Returns:
        Status of the operation
    """
    from ..server import get_client

    client = get_client()
    success = client.close_session(session_id)

    if success:
        return {"status": "stopped"}
    else:
        return {"status": "error", "message": "Session not found"}


def restart_debug(session_id: str) -> dict[str, Any]:
    """Restart the current debugging session with same parameters.

    Args:
        session_id: The session identifier

    Returns:
        New session_id and status
    """
    from ..server import get_client

    client = get_client()
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
    return start_debug(target, mode, args)
