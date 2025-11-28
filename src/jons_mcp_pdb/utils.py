"""Utility functions for jons-mcp-pdb."""

from typing import Any, TypeVar

from .constants import (
    CURRENT_LOCATION_PATTERN,
    DEFAULT_PAGINATION_OFFSET,
    STACK_FRAME_PATTERN,
)

T = TypeVar("T")


def apply_pagination(
    items: list[T],
    offset: int = DEFAULT_PAGINATION_OFFSET,
    limit: int | None = None,
) -> dict[str, Any]:
    """Apply pagination to a list of items.

    Args:
        items: The list of items to paginate.
        offset: Number of items to skip from the start.
        limit: Maximum number of items to return (None for all remaining).

    Returns:
        Dictionary containing paginated items and pagination metadata.
    """
    total_items = len(items)

    if limit is not None:
        paginated_items = items[offset : offset + limit]
    else:
        paginated_items = items[offset:]

    return {
        "items": paginated_items,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total_items,
            "returned": len(paginated_items),
        },
    }


def parse_location(output: str) -> dict[str, Any] | None:
    """Parse current location from PDB output.

    Args:
        output: Raw PDB output string.

    Returns:
        Dictionary with file, line, and function info, or None if not found.
    """
    match = CURRENT_LOCATION_PATTERN.search(output)
    if match:
        return {
            "file": match.group(1),
            "line": int(match.group(2)),
            "function": match.group(3).strip(),
        }
    return None


def parse_stack_frames(output: str) -> list[dict[str, Any]]:
    """Parse stack frames from 'where' command output.

    Args:
        output: Raw PDB 'where' command output.

    Returns:
        List of stack frame dictionaries.
    """
    frames = []
    lines = output.split("\n")

    for i, line in enumerate(lines):
        match = STACK_FRAME_PATTERN.match(line)
        if match:
            frames.append(
                {
                    "index": i,
                    "file": match.group(1).strip(),
                    "line": int(match.group(2)),
                    "function": match.group(3).strip(),
                    "code": "",
                }
            )

    return frames


def truncate_value(value: Any, max_length: int = 100) -> str:
    """Truncate a value's repr to a maximum length.

    Args:
        value: The value to represent.
        max_length: Maximum length of the string representation.

    Returns:
        Truncated string representation.
    """
    repr_value = repr(value)
    if len(repr_value) > max_length:
        return repr_value[: max_length - 3] + "..."
    return repr_value
