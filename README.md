# Jon's MCP PDB Server

A Model Context Protocol (MCP) server that provides Python debugging capabilities through subprocess-based pdb integration.

## Overview

The MCP PDB Server implements the Model Context Protocol to expose Python debugger (pdb) functionality. It manages pdb subprocess sessions, enabling MCP clients to control debugging of Python scripts, modules, and pytest tests through a standardized interface.

## Architecture

This implementation uses a subprocess-based architecture where:
- Each debug session spawns a separate Python process with pdb
- Communication happens via stdin/stdout pipes
- Thread-based I/O handling ensures non-blocking operations
- Sessions are managed independently, allowing multiple concurrent debugging sessions

## Features

- **Subprocess-based Debugging**: Debug Python scripts and modules in isolated processes
- **Session Management**: Create and manage multiple debugging sessions concurrently
- **Breakpoint Control**: Set, remove, enable/disable breakpoints with conditions
- **Execution Control**: Continue, step, next, return, and until commands
- **Stack Navigation**: Navigate up and down the call stack, view stack traces
- **Variable Inspection**: Examine variables, evaluate expressions, list locals/globals
- **Source Code Display**: View source code around current execution point
- **pytest Integration**: Debug pytest test suites with `--trace` flag
- **Virtual Environment Support**: Automatically detect and use virtual environments
- **Configuration Support**: Customize behavior via `pdbconfig.json`
- **Pagination Support**: All list operations support limit/offset pagination

## Installation

### Using uv (recommended)

```bash
# Clone the repository
git clone https://github.com/jonmmease/jons-mcp-pdb.git
cd jons-mcp-pdb

# Install and run
uv run jons-mcp-pdb
```

### Direct from GitHub

```bash
# Run directly from GitHub
uvx --from git+https://github.com/jonmmease/jons-mcp-pdb jons-mcp-pdb
```

### Adding to Claude Code as MCP Server

To use this with Claude Code, add it using the CLI:

```bash
# From GitHub (recommended)
claude mcp add jons-mcp-pdb -- uvx --from git+https://github.com/jonmmease/jons-mcp-pdb jons-mcp-pdb

# Local development
claude mcp add jons-mcp-pdb -- uv run --directory /path/to/jons-mcp-pdb jons-mcp-pdb
```

The server will be available in Claude Code for debugging Python scripts and pytest tests.

## Configuration

Create a `pdbconfig.json` file in your project root:

```json
{
  "python_path": null,              // Path to Python executable (null = auto-detect)
  "venv": ".venv",                  // Virtual environment directory name
  "working_directory": ".",         // Working directory for debugging
  "environment": {                  // Additional environment variables
    "PYTHONPATH": "./src",
    "DEBUG": "true"
  },
  "pytest_args": ["-v", "-s"]       // Additional pytest arguments
}
```

See `pdbconfig.json.example` for a template.

## MCP Tools

### Session Management

#### start_debug
Initialize a debugging session.
```
Args:
  target: Path to script or test file
  mode: "script" or "pytest" (required)
  args: Command line arguments (optional)
Returns:
  session_id: Unique session identifier
  status: "started" or error message
```

#### stop_debug
Terminate the active debugging session.
```
Args:
  session_id: The session identifier
Returns:
  status: "stopped" or error message
```

#### restart_debug
Restart the current debugging session with same parameters.
```
Args:
  session_id: The session identifier
Returns:
  session_id: New session identifier
  status: "restarted" or error message
```

### Breakpoint Management

#### set_breakpoint
Set a breakpoint at specified location.
```
Args:
  session_id: The session identifier
  file: File path (absolute or relative)
  line: Line number (optional if function specified)
  function: Function name (optional if line specified)
  condition: Conditional expression (optional)
  temporary: One-time breakpoint (default: false)
Returns:
  breakpoint_id: Unique breakpoint identifier
  location: Resolved file and line
```

#### remove_breakpoint
Remove a breakpoint.
```
Args:
  session_id: The session identifier
  breakpoint_id: Breakpoint identifier
Returns:
  status: "removed" or error message
```

#### list_breakpoints
List all breakpoints.
```
Args:
  session_id: The session identifier
  limit: Maximum breakpoints to return (optional)
  offset: Number to skip (default: 0)
Returns:
  breakpoints: Array of breakpoint objects
  pagination: Pagination metadata
```

#### enable_breakpoint / disable_breakpoint
Enable or disable a breakpoint.
```
Args:
  session_id: The session identifier
  breakpoint_id: Breakpoint identifier
Returns:
  status: New enabled state
```

### Execution Control

#### continue_execution
Continue execution until next breakpoint.
```
Args:
  session_id: The session identifier
Returns:
  stopped_at: Location where execution stopped
  reason: "breakpoint", "exception", "return", or "end"
```

#### step
Step into function calls (execute next line).
```
Args:
  session_id: The session identifier
Returns:
  location: New execution position
  entered_function: Function name if stepped into
```

#### next
Step over function calls (execute next line in current function).
```
Args:
  session_id: The session identifier
Returns:
  location: New execution position
```

#### return_from_function
Continue until current function returns.
```
Args:
  session_id: The session identifier
Returns:
  location: Return point
  return_value: Value being returned
```

#### until
Continue until specified line.
```
Args:
  session_id: The session identifier
  line: Target line number in current file
Returns:
  location: Where execution stopped
```

### Stack Navigation

#### where (alias: backtrace)
Get current stack trace.
```
Args:
  session_id: The session identifier
  limit: Maximum frames to return (optional)
  offset: Number to skip (default: 0)
Returns:
  frames: Array of stack frames
  pagination: Pagination metadata
```

#### up
Move up in the stack (to caller).
```
Args:
  session_id: The session identifier
  count: Number of frames to move (default: 1)
Returns:
  frame: New current frame information
```

#### down
Move down in the stack.
```
Args:
  session_id: The session identifier
  count: Number of frames to move (default: 1)
Returns:
  frame: New current frame information
```

### Inspection

#### list_source
Show source code around current or specified position.
```
Args:
  session_id: The session identifier
  line: Center line (optional, defaults to current)
  range: Number of lines before/after (default: 5)
  limit: Maximum lines to return (optional)
  offset: Number to skip (default: 0)
Returns:
  source: Source code lines with line numbers
  current_line: Currently executing line
  pagination: Pagination metadata
```

#### inspect_variable
Get detailed information about a variable.
```
Args:
  session_id: The session identifier
  name: Variable name
  frame: Stack frame index (optional, defaults to current)
  limit: Maximum attributes to return (optional)
  offset: Number to skip (default: 0)
Returns:
  name: Variable name
  value: String representation
  type: Type name
  attributes: Object attributes (for complex types)
  repr: repr() output
  str: str() output
  pagination: Pagination metadata (for attributes)
```

#### list_variables
List all variables in current scope.
```
Args:
  session_id: The session identifier
  frame: Stack frame index (optional)
  include_globals: Include global variables (default: false)
  limit: Maximum variables per category (optional)
  offset: Number to skip per category (default: 0)
Returns:
  locals: Local variables
  globals: Global variables (if requested)
  pagination: Pagination metadata
```

#### evaluate
Evaluate an expression in the current context.
```
Args:
  session_id: The session identifier
  expression: Python expression
  frame: Stack frame index (optional)
Returns:
  result: Evaluation result
  type: Result type
  error: Error message if evaluation failed
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run unit tests only (no subprocess spawning)
uv run pytest -m "not integration"

# Run integration tests only
uv run pytest -m integration

# Run with verbose output
uv run pytest -v
```

### Test Structure

- **Unit tests**: Test parsing, config loading, session management without subprocesses
- **Integration tests**: Spawn real pdb processes to test end-to-end behavior
- **Sample scripts**: Located in `tests/samples/`

## Virtual Environment Support

The server automatically detects and uses virtual environments in the following order:

1. Path specified in `python_path` configuration
2. Virtual environment specified in `venv` configuration
3. Common venv locations: `.venv`, `venv`, `.pixi/envs/default`
4. System Python as fallback

## Limitations

- Subprocess communication may have slight delays
- Large outputs might require pagination
- Some interactive pdb features may not work perfectly through subprocess pipes
- Concurrent debugging sessions are independent and cannot share state

## Troubleshooting

1. **Module not found errors**: Ensure the correct Python environment is being used
2. **Import errors**: Make sure dependencies are installed in the environment
3. **pytest not found**: Install pytest in the same environment
4. **Session not found**: Ensure you're using the correct session_id from start_debug
5. **Process terminated**: Check if the script completed or crashed - use list_source to see where it stopped
6. **Virtual environment issues**: Verify `python_path` in configuration points to the correct interpreter

## Development

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Type checking
uv run mypy src/jons_mcp_pdb

# Format code
uv run black src tests

# Lint code
uv run ruff check src tests
```

## License

MIT
