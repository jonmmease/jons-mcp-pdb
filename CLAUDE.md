# jons-mcp-pdb Development Guide

## Overview

MCP server providing Python debugging capabilities through subprocess-based pdb integration. Enables MCP clients (like Claude Code) to control debugging of Python scripts and pytest tests.

## Build Commands

```bash
# Install dependencies
uv pip install -e .

# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest                           # All tests
uv run pytest tests/test_pdb_client.py  # Specific file
uv run pytest -m integration            # Integration tests only
uv run pytest -m "not integration"      # Unit tests only

# Type checking
uv run mypy src/jons_mcp_pdb

# Linting
uv run ruff check src tests

# Formatting
uv run black src tests

# Run server
uv run jons-mcp-pdb
```

## Package Architecture

```
src/jons_mcp_pdb/
├── __init__.py           # Package exports (main, PdbClient, Config, etc.)
├── constants.py          # DebuggerState enum, regex patterns, timeouts
├── exceptions.py         # Custom exception classes
├── utils.py              # Pagination and parsing utilities
├── pdb_client.py         # PdbClient class (subprocess management)
├── server.py             # FastMCP server setup, lifespan, tool registration
└── tools/
    ├── __init__.py       # Tool re-exports
    ├── session.py        # start_debug, stop_debug, restart_debug
    ├── breakpoints.py    # set/remove/list/enable/disable_breakpoint
    ├── execution.py      # continue_execution, step, next_line, return_from_function, until
    ├── navigation.py     # where, backtrace, up, down
    └── inspection.py     # list_source, inspect_variable, list_variables, evaluate
```

## Key Patterns

### Session Management

Debug sessions are managed via `PdbClient`:
- Each session spawns a pdb subprocess
- Reader/writer threads handle async I/O
- Sessions are identified by string IDs (`session_1`, `session_2`, etc.)
- Global client instance accessed via `get_client()` in server.py

### Pagination

All list operations support pagination:
```python
def list_breakpoints(session_id: str, limit: int | None = None, offset: int = 0)
```

Response format:
```python
{
    "items": [...],
    "pagination": {
        "offset": 0,
        "limit": 10,
        "total": 25,
        "returned": 10
    }
}
```

### Tool Registration

Tools are defined in `tools/*.py` modules and registered in `server.py`:
```python
@mcp.tool()
def mcp_start_debug(...):
    return start_debug(...)
```

### Configuration

Loads from `pdbconfig.json` if present:
```json
{
  "python_path": "/usr/bin/python3",
  "venv": ".venv",
  "working_directory": ".",
  "environment": {"PYTHONPATH": "./src"},
  "pytest_args": ["-v", "-s"]
}
```

## Test Structure

- **Unit tests**: Test parsing, config loading, session management without subprocesses
- **Integration tests**: Marked with `@pytest.mark.integration`, spawn real pdb processes
- **Fixtures**: Defined in `tests/conftest.py` (client, test_script_path, etc.)
- **Sample scripts**: Located in `tests/samples/`

## MCP Registration

```bash
# Local development
claude mcp add jons-mcp-pdb -- uv run --directory /path/to/jons-mcp-pdb jons-mcp-pdb

# From GitHub
claude mcp add jons-mcp-pdb -- uvx --from git+https://github.com/jonmmease/jons-mcp-pdb jons-mcp-pdb
```
