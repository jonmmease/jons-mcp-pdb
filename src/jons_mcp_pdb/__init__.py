"""jons-mcp-pdb: MCP server for Python debugging via pdb."""

__version__ = "0.1.0"

from .pdb_client import Breakpoint, Config, DebugSession, PdbClient, StackFrame
from .server import main

__all__ = [
    "__version__",
    "main",
    "PdbClient",
    "Config",
    "Breakpoint",
    "StackFrame",
    "DebugSession",
]
