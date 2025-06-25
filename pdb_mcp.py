#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "fastmcp>=0.2.8",
#   "pytest>=7.0.0",
# ]
# ///

"""
FastMCP server that provides Python debugging capabilities through pdb.

This server manages in-process debugging sessions and exposes pdb features through MCP tools.
Run with: uv run pdb_mcp.py
"""

import pdb
import sys
import io
import traceback
import threading
import queue
import os
import json
import time
import runpy
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import logging
import signal
import atexit

from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "DEBUG"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastMCP server instance
mcp = FastMCP("pdb-mcp")

class DebuggerState(Enum):
    """States of the debugger"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"

@dataclass
class Breakpoint:
    """Represents a breakpoint"""
    id: int
    file: str
    line: int
    condition: Optional[str] = None
    temporary: bool = False
    enabled: bool = True
    hit_count: int = 0

@dataclass
class StackFrame:
    """Represents a stack frame"""
    index: int
    file: str
    line: int
    function: str
    code: str
    locals: Dict[str, Any] = field(default_factory=dict)

class QueueStdinAdapter(io.TextIOBase):
    """Adapter that makes a queue look like stdin to pdb"""
    
    def __init__(self, command_queue):
        self.command_queue = command_queue
        self._shutdown = False
        
    def readable(self):
        return True
        
    def readline(self, size=-1):
        """Read a line from the command queue"""
        logger.debug("QueueStdinAdapter.readline called")
        try:
            while not self._shutdown:
                try:
                    command = self.command_queue.get(timeout=0.1)
                    logger.debug(f"Got command from queue: {command}")
                    if command is None:  # Shutdown signal
                        self._shutdown = True
                        return "quit\n"
                    return command if command.endswith('\n') else command + '\n'
                except queue.Empty:
                    continue
            return "quit\n"
        except Exception as e:
            logger.error(f"Error in readline: {e}")
            return "quit\n"
    
    def shutdown(self):
        """Signal shutdown"""
        self._shutdown = True
        self.command_queue.put(None)

class CustomPdb(pdb.Pdb):
    """Custom Pdb class with enhanced features for MCP integration"""
    
    def __init__(self, output_buffer, command_queue=None, *args, **kwargs):
        self.output_buffer = output_buffer
        self.command_queue = command_queue or queue.Queue()
        self._stdin_adapter = QueueStdinAdapter(self.command_queue)
        
        kwargs['stdout'] = output_buffer
        kwargs['stdin'] = self._stdin_adapter
        
        super().__init__(*args, **kwargs)
        self.current_state = DebuggerState.IDLE
        self.last_command_output = ""
        self.breakpoint_hits = defaultdict(int)
        
    def trace_dispatch(self, frame, event, arg):
        """Override to track state changes"""
        if event == 'line':
            logger.debug(f"trace_dispatch: line event at {frame.f_code.co_filename}:{frame.f_lineno}")
            self.current_state = DebuggerState.PAUSED
            logger.debug("State set to PAUSED")
        elif event in ['call', 'return', 'exception']:
            logger.debug(f"trace_dispatch: {event} event at {frame.f_code.co_filename}:{frame.f_lineno}")
        return super().trace_dispatch(frame, event, arg)
    
    def do_quit(self, arg):
        """Override quit to update state"""
        logger.debug("do_quit called")
        self.current_state = DebuggerState.FINISHED
        return super().do_quit(arg)
    
    def do_continue(self, arg):
        """Override continue to update state"""
        logger.debug(f"do_continue called with arg: '{arg}'")
        self.current_state = DebuggerState.RUNNING
        result = super().do_continue(arg)
        logger.debug(f"do_continue returned: {result}")
        return result
    
    def user_line(self, frame):
        """Called when debugger stops at a line"""
        # Track breakpoint hits
        filename = self.canonic(frame.f_code.co_filename)
        lineno = frame.f_lineno
        bp_key = (filename, lineno)
        if bp_key in self.breaks:
            self.breakpoint_hits[bp_key] += 1
        super().user_line(frame)
    
    def shutdown(self):
        """Shutdown the debugger"""
        self._stdin_adapter.shutdown()

@dataclass
class DebugSession:
    """Represents a debugging session"""
    session_id: str
    debugger: CustomPdb
    output_buffer: io.StringIO
    error_buffer: io.StringIO
    command_queue: queue.Queue = field(default_factory=queue.Queue)
    breakpoints: Dict[int, Breakpoint] = field(default_factory=dict)
    next_breakpoint_id: int = 1
    thread: Optional[threading.Thread] = None
    target_type: str = "code"  # "code", "script", "module"
    target: str = ""
    args: List[str] = field(default_factory=list)
    globals_dict: Dict = field(default_factory=dict)
    locals_dict: Dict = field(default_factory=dict)
    exception_info: Optional[Dict] = None
    
    def get_state(self) -> DebuggerState:
        """Get current debugger state"""
        return self.debugger.current_state
    
    def send_command(self, command: str):
        """Send a command to the debugger"""
        logger.debug(f"Sending command to debugger: {command}")
        self.command_queue.put(command)

class PdbController:
    """Controller for managing pdb debugging sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, DebugSession] = {}
        self.lock = threading.Lock()
        self.session_counter = 0
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from pdbconfig.json if it exists"""
        config_path = Path.cwd() / "pdbconfig.json"
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load pdbconfig.json: {e}")
        return {}
    
    def create_session(self) -> str:
        """Create a new debugging session"""
        with self.lock:
            self.session_counter += 1
            session_id = f"session_{self.session_counter}"
            
            output_buffer = io.StringIO()
            error_buffer = io.StringIO()
            command_queue = queue.Queue()
            
            # Create custom pdb instance with command queue
            debugger = CustomPdb(
                output_buffer,
                command_queue,
                skip=['fastmcp*', 'mcp*', 'pdb*', 'bdb*', 'threading*']
            )
            
            session = DebugSession(
                session_id=session_id,
                debugger=debugger,
                output_buffer=output_buffer,
                error_buffer=error_buffer,
                command_queue=command_queue
            )
            
            self.sessions[session_id] = session
            return session_id
    
    def get_session(self, session_id: str) -> Optional[DebugSession]:
        """Get a session by ID"""
        return self.sessions.get(session_id)
    
    def close_session(self, session_id: str) -> bool:
        """Close and cleanup a session"""
        with self.lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                try:
                    # Send quit command
                    session.send_command("quit")
                    
                    # Shutdown the debugger
                    session.debugger.shutdown()
                    
                    # Wait for thread to finish
                    if session.thread and session.thread.is_alive():
                        session.thread.join(timeout=2.0)
                        
                except Exception as e:
                    logger.error(f"Error closing session: {e}")
                
                del self.sessions[session_id]
                return True
            return False
    
    def execute_code(self, session: DebugSession, code: str, filename: str = "<string>") -> Dict:
        """Run code in debug mode"""
        if session.get_state() == DebuggerState.RUNNING:
            return {"error": "Session is already running"}
        
        def debug_thread():
            try:
                session.debugger.current_state = DebuggerState.RUNNING
                session.target_type = "code"
                session.target = code
                
                # Clear buffers
                session.output_buffer.truncate(0)
                session.output_buffer.seek(0)
                session.error_buffer.truncate(0)
                session.error_buffer.seek(0)
                
                # Compile and run
                with redirect_stdout(session.output_buffer):
                    with redirect_stderr(session.error_buffer):
                        compiled = compile(code, filename, 'exec')
                        session.globals_dict = {}
                        
                        # If no breakpoints, just execute normally
                        if not session.breakpoints:
                            try:
                                exec(compiled, session.globals_dict, {})
                                session.debugger.current_state = DebuggerState.FINISHED
                                return
                            except Exception:
                                raise
                        
                        # Otherwise run with debugger
                        session.debugger.run(compiled, session.globals_dict, {})
                        
                        # The debugger will stop at the first line
                        # Send continue to actually start execution
                        if session.debugger.current_state in [DebuggerState.RUNNING, DebuggerState.PAUSED]:
                            logger.debug("Auto-continuing from first line...")
                            session.send_command("continue")
                        
            except Exception as e:
                logger.error(f"Exception in debug thread: {e}", exc_info=True)
                session.debugger.current_state = DebuggerState.ERROR
                session.exception_info = {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                }
                session.error_buffer.write(f"Error: {str(e)}\n")
                session.error_buffer.write(traceback.format_exc())
            finally:
                logger.debug(f"Debug thread ending, final state: {session.debugger.current_state.value}")
                if session.debugger.current_state == DebuggerState.RUNNING:
                    session.debugger.current_state = DebuggerState.FINISHED
        
        # Start debugging in a thread
        session.thread = threading.Thread(target=debug_thread)
        session.thread.start()
        
        # Wait a bit for it to start
        time.sleep(0.1)
        
        return {"status": "started"}
    
    def execute_script(self, session: DebugSession, script_path: str, args: List[str]) -> Dict:
        """Run a script in debug mode"""
        if session.get_state() == DebuggerState.RUNNING:
            return {"error": "Session is already running"}
        
        script_path = Path(script_path).resolve()
        if not script_path.exists():
            return {"error": f"Script not found: {script_path}"}
        
        def debug_thread():
            try:
                session.debugger.current_state = DebuggerState.RUNNING
                session.target_type = "script"
                session.target = str(script_path)
                session.args = args
                
                # Clear buffers
                session.output_buffer.truncate(0)
                session.output_buffer.seek(0)
                session.error_buffer.truncate(0)
                session.error_buffer.seek(0)
                
                # Set up sys.argv
                old_argv = sys.argv
                sys.argv = [str(script_path)] + args
                
                # Add script directory to path
                old_path = sys.path.copy()
                script_dir = str(script_path.parent)
                if script_dir not in sys.path:
                    sys.path.insert(0, script_dir)
                
                try:
                    with redirect_stdout(session.output_buffer):
                        with redirect_stderr(session.error_buffer):
                            # Read and compile the script
                            with open(script_path, 'r') as f:
                                code = f.read()
                            
                            compiled = compile(code, str(script_path), 'exec')
                            session.globals_dict = {
                                '__name__': '__main__',
                                '__file__': str(script_path)
                            }
                            
                            # Run with debugger
                            session.debugger.run(compiled, session.globals_dict, {})
                            
                            # Auto-continue from first line
                            if session.debugger.current_state in [DebuggerState.RUNNING, DebuggerState.PAUSED]:
                                logger.debug("Auto-continuing from first line...")
                                session.send_command("continue")
                                
                finally:
                    sys.argv = old_argv
                    sys.path = old_path
                    
            except Exception as e:
                logger.error(f"Exception in debug thread: {e}", exc_info=True)
                session.debugger.current_state = DebuggerState.ERROR
                session.exception_info = {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                }
                session.error_buffer.write(f"Error: {str(e)}\n")
                session.error_buffer.write(traceback.format_exc())
            finally:
                logger.debug(f"Debug thread ending, final state: {session.debugger.current_state.value}")
                if session.debugger.current_state == DebuggerState.RUNNING:
                    session.debugger.current_state = DebuggerState.FINISHED
        
        # Start debugging in a thread
        session.thread = threading.Thread(target=debug_thread)
        session.thread.start()
        
        # Wait a bit for it to start
        time.sleep(0.1)
        
        return {"status": "started"}
    
    def execute_module(self, session: DebugSession, module_name: str, args: List[str]) -> Dict:
        """Run a module in debug mode"""
        if session.get_state() == DebuggerState.RUNNING:
            return {"error": "Session is already running"}
        
        def debug_thread():
            try:
                session.debugger.current_state = DebuggerState.RUNNING
                session.target_type = "module"
                session.target = module_name
                session.args = args
                
                # Clear buffers
                session.output_buffer.truncate(0)
                session.output_buffer.seek(0)
                session.error_buffer.truncate(0)
                session.error_buffer.seek(0)
                
                # Set up sys.argv
                old_argv = sys.argv
                sys.argv = [module_name] + args
                
                try:
                    with redirect_stdout(session.output_buffer):
                        with redirect_stderr(session.error_buffer):
                            # Import and run the module
                            session.globals_dict = {}
                            
                            # For pytest, we need special handling
                            if module_name == "pytest":
                                try:
                                    import pytest
                                    logger.info(f"pytest found at: {pytest.__file__}")
                                except ImportError as e:
                                    logger.error(f"pytest not found in current environment: {e}")
                                    logger.error(f"Current Python: {sys.executable}")
                                    logger.error(f"You may need to run the MCP server with: {controller.get_python_executable()} -m uv run pdb_mcp.py")
                                    raise ImportError(
                                        f"pytest not found. The MCP server is running in {sys.executable}, "
                                        f"but your config expects {controller.get_python_executable()}. "
                                        f"Please ensure the MCP server is started with the correct Python environment."
                                    )
                                # Run pytest.main in a way that pdb can trace
                                code = f"import pytest; pytest.main({args!r})"
                                compiled = compile(code, "<pytest>", 'exec')
                                session.debugger.run(compiled, session.globals_dict, {})
                            else:
                                # Use runpy for other modules
                                import runpy
                                code = f"import runpy; runpy.run_module('{module_name}', run_name='__main__')"
                                compiled = compile(code, f"<module:{module_name}>", 'exec')
                                session.debugger.run(compiled, session.globals_dict, {})
                            
                            # Auto-continue from first line
                            if session.debugger.current_state in [DebuggerState.RUNNING, DebuggerState.PAUSED]:
                                logger.debug("Auto-continuing from first line...")
                                session.send_command("continue")
                                
                finally:
                    sys.argv = old_argv
                    
            except Exception as e:
                logger.error(f"Exception in debug thread: {e}", exc_info=True)
                session.debugger.current_state = DebuggerState.ERROR
                session.exception_info = {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                }
                session.error_buffer.write(f"Error: {str(e)}\n")
                session.error_buffer.write(traceback.format_exc())
            finally:
                logger.debug(f"Debug thread ending, final state: {session.debugger.current_state.value}")
                if session.debugger.current_state == DebuggerState.RUNNING:
                    session.debugger.current_state = DebuggerState.FINISHED
        
        # Start debugging in a thread
        session.thread = threading.Thread(target=debug_thread)
        session.thread.start()
        
        # Wait a bit for it to start
        time.sleep(0.1)
        
        return {"status": "started"}
    
    def set_breakpoint(self, session: DebugSession, filename: str = None, line: int = None, 
                      function: str = None, condition: str = None, temporary: bool = False) -> Dict:
        """Set a breakpoint"""
        if not filename and not function:
            return {"error": "Either filename/line or function must be specified"}
        
        if filename and line:
            # Set line breakpoint
            result = session.debugger.set_break(filename, line, temporary, condition, function)
            if result:
                bp_id = session.next_breakpoint_id
                session.next_breakpoint_id += 1
                
                bp = Breakpoint(
                    id=bp_id,
                    file=filename,
                    line=line,
                    condition=condition,
                    temporary=temporary,
                    enabled=True
                )
                session.breakpoints[bp_id] = bp
                
                return {
                    "breakpoint_id": bp_id,
                    "file": filename,
                    "line": line,
                    "condition": condition,
                    "temporary": temporary
                }
            else:
                return {"error": "Failed to set breakpoint"}
        
        elif function:
            # Set function breakpoint
            try:
                session.debugger.set_break(None, None, temporary, condition, function)
                bp_id = session.next_breakpoint_id
                session.next_breakpoint_id += 1
                
                bp = Breakpoint(
                    id=bp_id,
                    file="<function>",
                    line=0,
                    condition=condition,
                    temporary=temporary,
                    enabled=True
                )
                session.breakpoints[bp_id] = bp
                
                return {
                    "breakpoint_id": bp_id,
                    "function": function,
                    "condition": condition,
                    "temporary": temporary
                }
            except Exception as e:
                return {"error": f"Failed to set function breakpoint: {str(e)}"}
        
        return {"error": "Invalid breakpoint specification"}
    
    def get_python_executable(self) -> str:
        """Get the Python executable path based on configuration and environment"""
        # 1. Check config file
        if self.config.get("pythonPath"):
            return self.config["pythonPath"]
        
        # 2. Check environment variables
        if os.environ.get("VIRTUAL_ENV"):
            venv_python = Path(os.environ["VIRTUAL_ENV"]) / "bin" / "python"
            if venv_python.exists():
                return str(venv_python)
        
        if os.environ.get("CONDA_PREFIX"):
            conda_python = Path(os.environ["CONDA_PREFIX"]) / "bin" / "python"
            if conda_python.exists():
                return str(conda_python)
        
        # 3. Check common virtual environment directories
        venv_dir = self.config.get("venv", ".venv")
        for venv_name in [venv_dir, ".venv", "venv", ".pixi/envs/default", ".pixi/envs/dev"]:
            venv_path = Path.cwd() / venv_name
            if venv_path.exists():
                # Check for Python in different locations
                for python_rel_path in ["bin/python", "Scripts/python.exe"]:
                    python_path = venv_path / python_rel_path
                    if python_path.exists():
                        return str(python_path)
        
        # 4. Check user-installed Python (Unix-like systems)
        user_python = Path.home() / ".local" / "bin" / "python"
        if user_python.exists():
            return str(user_python)
        
        # 5. Use current Python interpreter as fallback
        return sys.executable

# Global controller instance
controller = PdbController()

# MCP Tool implementations

@mcp.tool()
def create_session() -> Dict[str, str]:
    """Create a new debugging session.
    
    Returns:
        Dictionary with session_id and status
    """
    session_id = controller.create_session()
    logger.info(f"Created debug session: {session_id}")
    return {
        "session_id": session_id,
        "status": "created"
    }

@mcp.tool()
def close_session(session_id: str) -> Dict[str, Any]:
    """Close a debugging session.
    
    Args:
        session_id: The session identifier
        
    Returns:
        Status of the operation
    """
    success = controller.close_session(session_id)
    if success:
        logger.info(f"Closed debug session: {session_id}")
        return {"status": "closed", "session_id": session_id}
    else:
        logger.error(f"Session not found: {session_id}")
        return {"error": "Session not found"}

@mcp.tool()
def run_code(
    session_id: str,
    code: str,
    filename: str = "<string>"
) -> Dict[str, Any]:
    """Run code in debug mode.
    
    Args:
        session_id: The session identifier
        code: Python code to execute
        filename: Optional filename for the code
        
    Returns:
        Execution status
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    result = controller.execute_code(session, code, filename)
    if "error" not in result:
        logger.info(f"Started debugging code in session {session_id}")
    return result

@mcp.tool()
def continue_execution(
    session_id: str
) -> Dict[str, Any]:
    """Continue execution until next breakpoint.
    
    Args:
        session_id: The session identifier
        
    Returns:
        Information about where execution stopped
    """
    logger.debug(f"continue_execution called for session {session_id}")
    
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    initial_state = session.get_state()
    logger.debug(f"Initial state: {initial_state.value}")
    
    if initial_state != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {initial_state.value})"}
    
    # Send continue command through the queue
    session.send_command("continue")
    
    # Wait for state to update with timeout
    logger.debug("Waiting for state update...")
    max_wait = 5.0  # 5 seconds max wait
    check_interval = 0.1
    elapsed = 0.0
    
    while elapsed < max_wait:
        current_state = session.get_state()
        logger.debug(f"After {elapsed:.1f}s - State: {current_state.value}")
        
        # If state changed from RUNNING, we're done waiting
        if current_state != DebuggerState.RUNNING:
            logger.debug(f"State changed to: {current_state.value}")
            break
            
        time.sleep(check_interval)
        elapsed += check_interval
    
    # Get final state
    final_state = session.get_state()
    output = session.output_buffer.getvalue()
    
    result = {
        "state": final_state.value,
        "output": output
    }
    
    if final_state == DebuggerState.PAUSED and session.debugger.curframe:
        result["stopped_at"] = {
            "file": session.debugger.curframe.f_code.co_filename,
            "line": session.debugger.curframe.f_lineno,
            "function": session.debugger.curframe.f_code.co_name
        }
        logger.info(f"Paused at {result['stopped_at']['file']}:{result['stopped_at']['line']}")
    elif final_state == DebuggerState.FINISHED:
        logger.info("Execution finished")
    elif final_state == DebuggerState.ERROR:
        result["exception"] = session.exception_info
        logger.error("Execution ended with error")
    
    return result

@mcp.tool()
def get_session_state(
    session_id: str
) -> Dict[str, Any]:
    """Get the current state of a debugging session.
    
    Args:
        session_id: The session identifier
        
    Returns:
        Current session state including location, variables, output
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    state = session.get_state()
    result = {
        "state": state.value,
        "output": session.output_buffer.getvalue(),
        "error": session.error_buffer.getvalue()
    }
    
    if state == DebuggerState.PAUSED and session.debugger.curframe:
        frame = session.debugger.curframe
        result["location"] = {
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno,
            "function": frame.f_code.co_name
        }
    
    return result

@mcp.tool()
def run_script(
    session_id: str,
    script_path: str,
    args: Optional[str] = None
) -> Dict[str, Any]:
    """Run a Python script in debug mode.
    
    Args:
        session_id: The session identifier
        script_path: Path to the Python script
        args: Script arguments (as list or JSON string)
        
    Returns:
        Execution status
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    # Parse args if it's a JSON string
    parsed_args = []
    if args:
        if isinstance(args, str):
            try:
                import json
                parsed_args = json.loads(args)
                if not isinstance(parsed_args, list):
                    parsed_args = [str(parsed_args)]
            except json.JSONDecodeError:
                # If not JSON, treat as a single argument
                parsed_args = [args]
        elif isinstance(args, list):
            parsed_args = args
    
    result = controller.execute_script(session, script_path, parsed_args)
    if "error" not in result:
        logger.info(f"Started debugging script {script_path} in session {session_id}")
    return result

@mcp.tool()
def run_module(
    session_id: str,
    module_name: str,
    args: Optional[str] = None
) -> Dict[str, Any]:
    """Run a Python module in debug mode.
    
    Args:
        session_id: The session identifier
        module_name: Name of the module to run (e.g., 'pytest')
        args: Module arguments (as list or JSON string)
        
    Returns:
        Execution status
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    # Parse args if it's a JSON string
    parsed_args = []
    if args:
        if isinstance(args, str):
            try:
                import json
                parsed_args = json.loads(args)
                if not isinstance(parsed_args, list):
                    parsed_args = [str(parsed_args)]
            except json.JSONDecodeError:
                # If not JSON, treat as a single argument
                parsed_args = [args]
        elif isinstance(args, list):
            parsed_args = args
    
    result = controller.execute_module(session, module_name, parsed_args)
    if "error" not in result:
        logger.info(f"Started debugging module {module_name} in session {session_id}")
    return result

@mcp.tool()
def set_breakpoint(
    session_id: str,
    filename: Optional[str] = None,
    line: Optional[int] = None,
    function: Optional[str] = None,
    condition: Optional[str] = None,
    temporary: bool = False
) -> Dict[str, Any]:
    """Set a breakpoint.
    
    Args:
        session_id: The session identifier
        filename: File path for line breakpoint
        line: Line number for line breakpoint
        function: Function name for function breakpoint
        condition: Optional condition expression
        temporary: Whether breakpoint is temporary
        
    Returns:
        Breakpoint information or error
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    result = controller.set_breakpoint(session, filename, line, function, condition, temporary)
    if "error" not in result:
        logger.info(f"Set breakpoint in session {session_id}: {result}")
    return result

@mcp.tool()
def remove_breakpoint(
    session_id: str,
    breakpoint_id: int
) -> Dict[str, Any]:
    """Remove a breakpoint.
    
    Args:
        session_id: The session identifier
        breakpoint_id: The breakpoint ID to remove
        
    Returns:
        Status of the operation
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if breakpoint_id not in session.breakpoints:
        return {"error": f"Breakpoint {breakpoint_id} not found"}
    
    bp = session.breakpoints[breakpoint_id]
    try:
        # Clear the breakpoint in pdb
        session.debugger.clear_break(bp.file, bp.line)
        del session.breakpoints[breakpoint_id]
        logger.info(f"Removed breakpoint {breakpoint_id} from session {session_id}")
        return {"status": "removed", "breakpoint_id": breakpoint_id}
    except Exception as e:
        return {"error": f"Failed to remove breakpoint: {str(e)}"}

@mcp.tool()
def list_breakpoints(
    session_id: str
) -> Dict[str, Any]:
    """List all breakpoints in a session.
    
    Args:
        session_id: The session identifier
        
    Returns:
        List of breakpoints
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    breakpoints = []
    for bp_id, bp in session.breakpoints.items():
        bp_info = {
            "id": bp_id,
            "file": bp.file,
            "line": bp.line,
            "enabled": bp.enabled,
            "temporary": bp.temporary,
            "hit_count": bp.hit_count
        }
        if bp.condition:
            bp_info["condition"] = bp.condition
        breakpoints.append(bp_info)
    
    return {"breakpoints": breakpoints}

@mcp.tool()
def step(
    session_id: str
) -> Dict[str, Any]:
    """Step into function calls.
    
    Args:
        session_id: The session identifier
        
    Returns:
        Information about where execution stopped
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    # Send step command
    session.send_command("step")
    
    # Wait for state to update
    time.sleep(0.2)
    
    state = session.get_state()
    result = {
        "state": state.value,
        "output": session.output_buffer.getvalue()
    }
    
    if state == DebuggerState.PAUSED and session.debugger.curframe:
        result["stopped_at"] = {
            "file": session.debugger.curframe.f_code.co_filename,
            "line": session.debugger.curframe.f_lineno,
            "function": session.debugger.curframe.f_code.co_name
        }
        logger.info(f"Stepped to {result['stopped_at']['file']}:{result['stopped_at']['line']}")
    
    return result

@mcp.tool()
def step_over(
    session_id: str
) -> Dict[str, Any]:
    """Step over function calls.
    
    Args:
        session_id: The session identifier
        
    Returns:
        Information about where execution stopped
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    # Send next command
    session.send_command("next")
    
    # Wait for state to update
    time.sleep(0.2)
    
    state = session.get_state()
    result = {
        "state": state.value,
        "output": session.output_buffer.getvalue()
    }
    
    if state == DebuggerState.PAUSED and session.debugger.curframe:
        result["stopped_at"] = {
            "file": session.debugger.curframe.f_code.co_filename,
            "line": session.debugger.curframe.f_lineno,
            "function": session.debugger.curframe.f_code.co_name
        }
        logger.info(f"Stepped over to {result['stopped_at']['file']}:{result['stopped_at']['line']}")
    
    return result

@mcp.tool()
def return_from_function(
    session_id: str
) -> Dict[str, Any]:
    """Continue execution until the current function returns.
    
    Args:
        session_id: The session identifier
        
    Returns:
        Information about where execution stopped
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    # Send return command
    session.send_command("return")
    
    # Wait for state to update
    max_wait = 5.0
    check_interval = 0.1
    elapsed = 0.0
    
    while elapsed < max_wait:
        current_state = session.get_state()
        if current_state != DebuggerState.RUNNING:
            break
        time.sleep(check_interval)
        elapsed += check_interval
    
    state = session.get_state()
    result = {
        "state": state.value,
        "output": session.output_buffer.getvalue()
    }
    
    if state == DebuggerState.PAUSED and session.debugger.curframe:
        result["stopped_at"] = {
            "file": session.debugger.curframe.f_code.co_filename,
            "line": session.debugger.curframe.f_lineno,
            "function": session.debugger.curframe.f_code.co_name
        }
        logger.info(f"Returned to {result['stopped_at']['file']}:{result['stopped_at']['line']}")
    
    return result

@mcp.tool()
def where(
    session_id: str,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """Get the current stack trace.
    
    Args:
        session_id: The session identifier
        limit: Maximum number of frames to return
        
    Returns:
        Stack trace information
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    if not session.debugger.curframe:
        return {"error": "No stack frame available"}
    
    # Get stack trace
    stack_frames = []
    frame = session.debugger.curframe
    index = session.debugger.curindex
    
    # Go up to top of stack
    while frame.f_back and index > 0:
        frame = frame.f_back
        index -= 1
    
    # Now collect frames from top to bottom
    frame_count = 0
    while frame:
        if limit and frame_count >= limit:
            break
            
        stack_frames.append({
            "index": frame_count,
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno,
            "function": frame.f_code.co_name,
            "current": frame_count == session.debugger.curindex
        })
        
        frame = frame.f_back if hasattr(frame, 'f_back') else None
        frame_count += 1
    
    # Reverse to show most recent first
    stack_frames.reverse()
    
    return {
        "frames": stack_frames,
        "current_index": session.debugger.curindex
    }

@mcp.tool()
def up(
    session_id: str,
    count: int = 1
) -> Dict[str, Any]:
    """Move up in the stack frame.
    
    Args:
        session_id: The session identifier
        count: Number of frames to move up
        
    Returns:
        New stack location
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    # Send up commands
    for _ in range(count):
        session.send_command("up")
    
    # Get current location
    time.sleep(0.1)
    
    if session.debugger.curframe:
        return {
            "location": {
                "file": session.debugger.curframe.f_code.co_filename,
                "line": session.debugger.curframe.f_lineno,
                "function": session.debugger.curframe.f_code.co_name,
                "index": session.debugger.curindex
            }
        }
    
    return {"error": "Failed to move up in stack"}

@mcp.tool()
def down(
    session_id: str,
    count: int = 1
) -> Dict[str, Any]:
    """Move down in the stack frame.
    
    Args:
        session_id: The session identifier
        count: Number of frames to move down
        
    Returns:
        New stack location
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    # Send down commands
    for _ in range(count):
        session.send_command("down")
    
    # Get current location
    time.sleep(0.1)
    
    if session.debugger.curframe:
        return {
            "location": {
                "file": session.debugger.curframe.f_code.co_filename,
                "line": session.debugger.curframe.f_lineno,
                "function": session.debugger.curframe.f_code.co_name,
                "index": session.debugger.curindex
            }
        }
    
    return {"error": "Failed to move down in stack"}

@mcp.tool()
def list_source(
    session_id: str,
    line: Optional[int] = None,
    context_range: int = 5
) -> Dict[str, Any]:
    """List source code around current line or specified line.
    
    Args:
        session_id: The session identifier
        line: Line number to show (default: current line)
        context_range: Number of lines before/after to show
        
    Returns:
        Source code listing
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    if not session.debugger.curframe:
        return {"error": "No current frame"}
    
    filename = session.debugger.curframe.f_code.co_filename
    current_line = line or session.debugger.curframe.f_lineno
    
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
        
        start = max(1, current_line - context_range)
        end = min(len(lines) + 1, current_line + context_range + 1)
        
        source_lines = []
        for i in range(start, end):
            prefix = "-> " if i == session.debugger.curframe.f_lineno else "   "
            source_lines.append({
                "line": i,
                "text": lines[i-1].rstrip(),
                "current": i == session.debugger.curframe.f_lineno
            })
        
        return {
            "file": filename,
            "lines": source_lines,
            "current_line": session.debugger.curframe.f_lineno
        }
    except Exception as e:
        return {"error": f"Failed to read source: {str(e)}"}

@mcp.tool()
def list_variables(
    session_id: str,
    include_globals: bool = False
) -> Dict[str, Any]:
    """List variables in current scope.
    
    Args:
        session_id: The session identifier
        include_globals: Whether to include global variables
        
    Returns:
        Variable information
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    if not session.debugger.curframe:
        return {"error": "No current frame"}
    
    frame = session.debugger.curframe
    
    # Get local variables
    locals_dict = {}
    for name, value in frame.f_locals.items():
        try:
            locals_dict[name] = {
                "type": type(value).__name__,
                "value": repr(value)[:100]  # Truncate long representations
            }
        except Exception:
            locals_dict[name] = {
                "type": "unknown",
                "value": "<error getting value>"
            }
    
    result = {"locals": locals_dict}
    
    # Get global variables if requested
    if include_globals:
        globals_dict = {}
        for name, value in frame.f_globals.items():
            if not name.startswith('__'):  # Skip dunder variables
                try:
                    globals_dict[name] = {
                        "type": type(value).__name__,
                        "value": repr(value)[:100]
                    }
                except Exception:
                    globals_dict[name] = {
                        "type": "unknown",
                        "value": "<error getting value>"
                    }
        result["globals"] = globals_dict
    
    return result

@mcp.tool()
def inspect_variable(
    session_id: str,
    name: str
) -> Dict[str, Any]:
    """Get detailed information about a variable.
    
    Args:
        session_id: The session identifier
        name: Variable name to inspect
        
    Returns:
        Detailed variable information
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    if not session.debugger.curframe:
        return {"error": "No current frame"}
    
    frame = session.debugger.curframe
    
    # Check locals first, then globals
    if name in frame.f_locals:
        value = frame.f_locals[name]
    elif name in frame.f_globals:
        value = frame.f_globals[name]
    else:
        return {"error": f"Variable '{name}' not found"}
    
    try:
        result = {
            "name": name,
            "type": type(value).__name__,
            "value": repr(value),
            "str": str(value)
        }
        
        # Add additional info based on type
        if hasattr(value, '__dict__'):
            attrs = {}
            for attr_name in dir(value):
                if not attr_name.startswith('_'):
                    try:
                        attrs[attr_name] = repr(getattr(value, attr_name))[:100]
                    except Exception:
                        attrs[attr_name] = "<error getting attribute>"
            result["attributes"] = attrs
        
        if hasattr(value, '__len__'):
            result["length"] = len(value)
        
        return result
    except Exception as e:
        return {"error": f"Failed to inspect variable: {str(e)}"}

@mcp.tool()
def evaluate(
    session_id: str,
    expression: str
) -> Dict[str, Any]:
    """Evaluate an expression in the current context.
    
    Args:
        session_id: The session identifier
        expression: Python expression to evaluate
        
    Returns:
        Evaluation result
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    if session.get_state() != DebuggerState.PAUSED:
        return {"error": f"Debugger is not paused (state: {session.get_state().value})"}
    
    if not session.debugger.curframe:
        return {"error": "No current frame"}
    
    frame = session.debugger.curframe
    
    try:
        # Evaluate expression in current frame context
        result = eval(expression, frame.f_globals, frame.f_locals)
        return {
            "expression": expression,
            "result": repr(result),
            "type": type(result).__name__
        }
    except Exception as e:
        return {
            "expression": expression,
            "error": str(e),
            "type": type(e).__name__
        }

@mcp.tool()
def restart_session(
    session_id: str
) -> Dict[str, Any]:
    """Restart the debugging session with the same target.
    
    Args:
        session_id: The session identifier
        
    Returns:
        Status of the restart
    """
    session = controller.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    # Save target info
    target_type = session.target_type
    target = session.target
    args = session.args
    
    # Stop current execution
    if session.get_state() == DebuggerState.RUNNING:
        session.send_command("quit")
        time.sleep(0.5)
    
    # Restart based on target type
    if target_type == "code":
        return controller.execute_code(session, target)
    elif target_type == "script":
        return controller.execute_script(session, target, args)
    elif target_type == "module":
        return controller.execute_module(session, target, args)
    else:
        return {"error": "No target to restart"}

@mcp.tool()
def create_config() -> Dict[str, Any]:
    """Create a template pdbconfig.json file.
    
    Returns:
        Status of config creation
    """
    config_template = {
        "pythonPath": "",
        "venv": ".venv",
        "workingDirectory": ".",
        "environment": {},
        "breakOnException": True,
        "followForks": False
    }
    
    config_path = Path.cwd() / "pdbconfig.json"
    if config_path.exists():
        return {"error": "pdbconfig.json already exists"}
    
    try:
        with open(config_path, 'w') as f:
            json.dump(config_template, f, indent=2)
        return {
            "status": "created",
            "path": str(config_path),
            "content": config_template
        }
    except Exception as e:
        return {"error": f"Failed to create config: {str(e)}"}

# Cleanup function
def cleanup():
    """Ensure all debugging sessions are closed when the MCP server exits."""
    logger.info("Running cleanup...")
    for session_id in list(controller.sessions.keys()):
        try:
            controller.close_session(session_id)
        except Exception as e:
            logger.error(f"Error closing session {session_id}: {e}")
    logger.info("Cleanup complete")

# Register cleanup handler
atexit.register(cleanup)

# Main entry point
def main():
    """Initialize and run the FastMCP server."""
    logger.info("Starting MCP PDB Tool Server")
    logger.info(f"Python Executable: {sys.executable}")
    logger.info(f"Working Directory: {os.getcwd()}")
    
    # Log the Python environment being used
    logger.info(f"Python Version: {sys.version}")
    logger.info(f"Python Path: {sys.path[:3]}...")  # First 3 paths
    
    # Check what environment we're in
    if os.environ.get("VIRTUAL_ENV"):
        logger.info(f"VIRTUAL_ENV: {os.environ['VIRTUAL_ENV']}")
    if os.environ.get("CONDA_PREFIX"):
        logger.info(f"CONDA_PREFIX: {os.environ['CONDA_PREFIX']}")
    
    # Log the configured Python executable
    config_python = controller.get_python_executable()
    logger.info(f"Configured Python (from config/env): {config_python}")
    
    # Handle keyboard interrupt gracefully
    def signal_handler(sig, frame):
        logger.info("Received interrupt signal, shutting down...")
        cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run the server
    mcp.run()
    logger.info("MCP PDB Tool Server Shutdown")

if __name__ == "__main__":
    main()