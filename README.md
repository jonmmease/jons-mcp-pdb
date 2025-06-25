# MCP PDB Server

A Model Context Protocol (MCP) server that provides Python debugging capabilities through pdb.

## Features

- **In-Process Debugging**: Debug Python code, scripts, and modules directly within the MCP server process
- **Session Management**: Create and manage multiple debugging sessions concurrently
- **Breakpoint Control**: Set, remove, and list breakpoints with conditions
- **Execution Control**: Step through code, continue execution, and navigate stack frames
- **Variable Inspection**: Examine variables, evaluate expressions, and view local/global scope
- **Source Code Display**: View source code around current execution point
- **Configuration Support**: Optional `pdbconfig.json` for Python interpreter and environment settings

## Installation

```bash
# Using uv (recommended)
uv run pdb_mcp.py

# Or with pip
pip install fastmcp>=0.2.8
python pdb_mcp.py
```

## Usage

The server exposes the following MCP tools:

### Session Management
- `create_session()` - Create a new debugging session
- `close_session(session_id)` - Close a debugging session
- `get_session_state(session_id)` - Get current session state
- `restart_session(session_id)` - Restart session with same target

### Running Code
- `run_code(session_id, code, filename)` - Debug Python code snippet
- `run_script(session_id, script_path, args)` - Debug Python script file
- `run_module(session_id, module_name, args)` - Debug Python module

### Breakpoints
- `set_breakpoint(session_id, filename, line, function, condition, temporary)` - Set breakpoint
- `remove_breakpoint(session_id, breakpoint_id)` - Remove breakpoint
- `list_breakpoints(session_id)` - List all breakpoints

### Execution Control
- `continue_execution(session_id)` - Continue until next breakpoint
- `step(session_id)` - Step into function calls
- `step_over(session_id)` - Step over function calls
- `return_from_function(session_id)` - Continue until function returns

### Stack Navigation
- `where(session_id, limit)` - Get stack trace
- `up(session_id, count)` - Move up in stack
- `down(session_id, count)` - Move down in stack

### Inspection
- `list_source(session_id, line, context_range)` - Show source code
- `list_variables(session_id, include_globals)` - List variables in scope
- `inspect_variable(session_id, name)` - Get variable details
- `evaluate(session_id, expression)` - Evaluate expression

### Configuration
- `create_config()` - Create pdbconfig.json template

## Configuration

Create a `pdbconfig.json` file in your project root:

```json
{
  "pythonPath": "",           // Path to Python executable (empty = auto-detect)
  "venv": ".venv",           // Virtual environment directory
  "workingDirectory": ".",    // Working directory for debugging
  "environment": {},         // Additional environment variables
  "breakOnException": true,  // Break on uncaught exceptions
  "followForks": false      // Follow forked processes
}
```

## Example Usage

```python
# Create a debugging session
session = create_session()
session_id = session["session_id"]

# Run a script with a breakpoint
set_breakpoint(session_id, "test_pdb.py", line=6)
run_script(session_id, "test_pdb.py")

# Continue execution
continue_execution(session_id)

# Inspect variables
vars = list_variables(session_id)
inspect_variable(session_id, "n")

# Step through code
step(session_id)
step_over(session_id)

# Get stack trace
where(session_id)

# Close session
close_session(session_id)
```

## Virtual Environment Support

The server automatically detects and uses virtual environments in the following order:
1. `VIRTUAL_ENV` environment variable
2. `CONDA_PREFIX` environment variable  
3. Common venv directories: `.venv`, `venv`, `.pixi/envs/default`, `.pixi/envs/dev`
4. User-installed Python in `~/.local/bin` (Unix)
5. System Python as fallback

## Limitations

- Debugging runs in separate threads to avoid blocking the MCP server
- Some pdb features may behave differently in the threaded environment
- Large output from debugged programs may be truncated

## License

MIT