"""Inspection tools for pdb debugging."""

from typing import Any

from ..constants import PDB_PROMPT


def list_source(
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
    from ..server import get_client

    client = get_client()

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

    # Parse source lines for pagination
    source_output = result["output"]
    source_lines = source_output.split("\n")

    # Remove pdb prompt and empty lines at the end
    while source_lines and (
        not source_lines[-1].strip() or source_lines[-1].strip() == "(Pdb)"
    ):
        source_lines.pop()

    total_lines = len(source_lines)

    # Apply pagination
    if limit is not None:
        paginated_lines = source_lines[offset : offset + limit]
    else:
        paginated_lines = source_lines[offset:]

    paginated_source = "\n".join(paginated_lines)

    return {
        "source": paginated_source,
        "current_line": current_line,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total_lines,
            "returned": len(paginated_lines),
        },
    }


def inspect_variable(
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
    from ..server import get_client

    client = get_client()

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
    all_attributes: dict[str, str] = {}
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
                            all_attributes[attr] = (
                                attr_result["output"].replace(PDB_PROMPT, "").strip()
                            )
            except Exception:
                pass

    # Apply pagination to attributes
    attr_items = list(all_attributes.items())
    total_attributes = len(attr_items)

    if limit is not None:
        paginated_attributes = dict(attr_items[offset : offset + limit])
    else:
        paginated_attributes = dict(attr_items[offset:])

    # Switch back frame if needed
    if frame is not None:
        client.send_command(session_id, f"down {frame}")

    response: dict[str, Any] = {
        "name": name,
        "value": value,
        "type": type_name,
        "attributes": paginated_attributes,
        "repr": repr_value,
        "str": value,
    }

    # Add pagination info if there are attributes
    if total_attributes > 0:
        response["pagination"] = {
            "attributes": {
                "offset": offset,
                "limit": limit,
                "total": total_attributes,
                "returned": len(paginated_attributes),
            }
        }

    return response


def list_variables(
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
    from ..server import get_client

    client = get_client()

    # Switch frame if needed
    if frame is not None:
        result = client.send_command(session_id, f"up {frame}")
        if "error" in result:
            return result

    # Get locals
    locals_result = client.send_command(session_id, "p locals()")
    if "error" in locals_result:
        return locals_result

    locals_dict: dict[str, str] = {}
    try:
        locals_str = locals_result["output"].replace(PDB_PROMPT, "").strip()
        locals_raw = eval(locals_str)
        for k, v in locals_raw.items():
            locals_dict[k] = repr(v)[:100]  # Truncate long values
    except Exception:
        pass

    # Apply pagination to locals
    locals_items = list(locals_dict.items())
    locals_total = len(locals_items)

    if limit is not None:
        locals_paginated = dict(locals_items[offset : offset + limit])
    else:
        locals_paginated = dict(locals_items[offset:])

    result_dict: dict[str, Any] = {
        "locals": locals_paginated,
        "pagination": {
            "locals": {
                "offset": offset,
                "limit": limit,
                "total": locals_total,
                "returned": len(locals_paginated),
            }
        },
    }

    # Get globals if requested
    if include_globals:
        globals_result = client.send_command(session_id, "p globals()")
        if "error" not in globals_result:
            globals_dict: dict[str, str] = {}
            try:
                globals_str = globals_result["output"].replace(PDB_PROMPT, "").strip()
                globals_raw = eval(globals_str)
                for k, v in globals_raw.items():
                    if not k.startswith("__"):  # Skip dunder variables
                        globals_dict[k] = repr(v)[:100]
            except Exception:
                pass

            # Apply pagination to globals
            globals_items = list(globals_dict.items())
            globals_total = len(globals_items)

            if limit is not None:
                globals_paginated = dict(globals_items[offset : offset + limit])
            else:
                globals_paginated = dict(globals_items[offset:])

            result_dict["globals"] = globals_paginated
            result_dict["pagination"]["globals"] = {
                "offset": offset,
                "limit": limit,
                "total": globals_total,
                "returned": len(globals_paginated),
            }

    # Switch back frame if needed
    if frame is not None:
        client.send_command(session_id, f"down {frame}")

    return result_dict


def evaluate(
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
    from ..server import get_client

    client = get_client()

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
