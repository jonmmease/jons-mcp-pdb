# MCP Python Debugger Server Proposal

## Overview

The MCP PDB Server will provide a Model Context Protocol interface to the Python debugger (pdb), enabling MCP clients to control debugging sessions for Python scripts and pytest tests. This will be implemented as a single-file uv script using fastmcp, following the pattern established by mcp-pyright.

## Architecture

### Core Components

1. **PdbClient Class**
   - Manages pdb subprocess lifecycle
   - Handles bidirectional communication via stdin/stdout
   - Parses pdb output into structured data
   - Maintains debugging session state
   - Thread-based I/O handling for non-blocking operations

2. **Session Management**
   - Support for debugging Python scripts: `python -m pdb script.py`
   - Support for pytest debugging: `pytest --pdb test_file.py`
   - Automatic virtual environment detection
   - Graceful shutdown and cleanup

3. **State Tracking**
   - Current execution position (file, line, function)
   - Active breakpoints and their states
   - Stack frame information
   - Variable scopes and values

## Configuration

### pdbconfig.json Structure

```json
{
  "pythonPath": "/path/to/python",  // Optional, auto-detected if not specified
  "venv": ".venv",                   // Virtual environment directory
  "workingDirectory": ".",           // Working directory for debugging
  "environment": {                   // Additional environment variables
    "PYTHONPATH": "./src"
  },
  "debugMode": "script",             // "script" or "pytest"
  "pytestArgs": ["-v", "-s"],       // Additional pytest arguments
  "breakOnException": true,          // Break on uncaught exceptions
  "followForks": false              // Follow forked processes
}
```

## MCP Tools

### Session Management Tools

#### start_debug
Initialize a debugging session.
```
Args:
  target: Path to script or test file
  args: Command line arguments (optional)
  mode: "script" or "pytest" (optional, defaults to config)
Returns:
  session_id: Unique session identifier
  status: "started" or error message
```

#### stop_debug
Terminate the active debugging session.
```
Returns:
  status: "stopped" or error message
```

#### restart_debug
Restart the current debugging session with same parameters.
```
Returns:
  session_id: New session identifier
  status: "restarted" or error message
```

### Breakpoint Management Tools

#### set_breakpoint
Set a breakpoint at specified location.
```
Args:
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
  breakpoint_id: Breakpoint identifier
Returns:
  status: "removed" or error message
```

#### list_breakpoints
List all breakpoints.
```
Returns:
  breakpoints: Array of breakpoint objects
    - id: Breakpoint identifier
    - file: File path
    - line: Line number
    - function: Function name (if applicable)
    - condition: Condition expression
    - enabled: true/false
    - hit_count: Number of times hit
```

#### enable_breakpoint / disable_breakpoint
Enable or disable a breakpoint.
```
Args:
  breakpoint_id: Breakpoint identifier
Returns:
  status: New enabled state
```

### Execution Control Tools

#### continue
Continue execution until next breakpoint.
```
Returns:
  stopped_at: Location where execution stopped
  reason: "breakpoint", "exception", "return", or "end"
```

#### step
Step into function calls (execute next line).
```
Returns:
  location: New execution position
  entered_function: Function name if stepped into
```

#### next
Step over function calls (execute next line in current function).
```
Returns:
  location: New execution position
```

#### return
Continue until current function returns.
```
Returns:
  location: Return point
  return_value: Value being returned
```

#### until
Continue until specified line.
```
Args:
  line: Target line number in current file
Returns:
  location: Where execution stopped
```

### Stack Navigation Tools

#### where (alias: backtrace)
Get current stack trace.
```
Args:
  limit: Maximum frames to return (optional)
Returns:
  frames: Array of stack frames
    - index: Frame index (0 = current)
    - file: File path
    - line: Line number
    - function: Function name
    - code: Line of code
```

#### up
Move up in the stack (to caller).
```
Args:
  count: Number of frames to move (default: 1)
Returns:
  frame: New current frame information
```

#### down
Move down in the stack.
```
Args:
  count: Number of frames to move (default: 1)
Returns:
  frame: New current frame information
```

### Inspection Tools

#### list_source
Show source code around current or specified position.
```
Args:
  line: Center line (optional, defaults to current)
  range: Number of lines before/after (default: 5)
Returns:
  source: Source code lines with line numbers
  current_line: Currently executing line
```

#### inspect_variable
Get detailed information about a variable.
```
Args:
  name: Variable name
  frame: Stack frame index (optional, defaults to current)
Returns:
  name: Variable name
  value: String representation
  type: Type name
  attributes: Object attributes (for complex types)
  repr: repr() output
  str: str() output
```

#### list_variables
List all variables in current scope.
```
Args:
  frame: Stack frame index (optional)
  include_globals: Include global variables (default: false)
Returns:
  locals: Local variables
  globals: Global variables (if requested)
```

#### evaluate
Evaluate an expression in the current context.
```
Args:
  expression: Python expression
  frame: Stack frame index (optional)
Returns:
  result: Evaluation result
  type: Result type
  error: Error message if evaluation failed
```

## Implementation Approach

### 1. Subprocess Communication
- Use subprocess.Popen with pipes for stdin/stdout/stderr
- Implement thread-based readers to avoid blocking
- Queue-based message passing between threads and async handlers

### 2. Output Parsing
- Regular expressions to identify pdb prompts and responses
- State machine to track pdb mode (normal, post-mortem, etc.)
- Structured parsing of stack traces, variable listings, etc.

### 3. Error Handling
- Graceful handling of pdb crashes
- Timeout mechanisms for hung operations
- Clear error messages for MCP clients

### 4. Virtual Environment Support
- Auto-detect common venv locations (.venv, venv, .pixi/envs/*)
- Support conda/pixi environment activation
- Respect pythonPath in configuration

## Example Usage

```python
# Start debugging a script
await start_debug(target="my_script.py", args=["--input", "data.csv"])

# Set a breakpoint
bp = await set_breakpoint(file="my_script.py", line=42)

# Continue execution
result = await continue()
# Returns: {"stopped_at": {"file": "my_script.py", "line": 42}, "reason": "breakpoint"}

# Inspect variables
vars = await list_variables()
# Returns: {"locals": {"x": 10, "data": "[1, 2, 3]"}, "globals": {...}}

# Evaluate expression
result = await evaluate(expression="len(data)")
# Returns: {"result": "3", "type": "int"}

# Step through code
await step()
await next()

# Get stack trace
stack = await where()
# Returns detailed stack information
```

## Benefits

1. **IDE Integration**: Enable rich debugging features in any MCP-compatible editor
2. **Automation**: Script debugging sessions for testing and analysis
3. **Remote Debugging**: Debug Python applications running in containers or remote systems
4. **Consistency**: Uniform debugging interface across different environments
5. **Extensibility**: Easy to add new debugging features as MCP tools

## Next Steps

1. Implement core PdbClient class with subprocess management
2. Create output parsers for pdb responses
3. Implement all MCP tools with proper error handling
4. Add comprehensive logging and debugging capabilities
5. Create test suite for various debugging scenarios
6. Write documentation and usage examples