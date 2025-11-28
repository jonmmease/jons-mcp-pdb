"""MCP tools for Python debugging."""

# Session management tools
# Breakpoint management tools
from .breakpoints import (
    disable_breakpoint,
    enable_breakpoint,
    list_breakpoints,
    remove_breakpoint,
    set_breakpoint,
)

# Execution control tools
from .execution import (
    continue_execution,
    next_line,
    return_from_function,
    step,
    until,
)

# Inspection tools
from .inspection import evaluate, inspect_variable, list_source, list_variables

# Stack navigation tools
from .navigation import backtrace, down, up, where
from .session import restart_debug, start_debug, stop_debug

__all__ = [
    # Session management
    "start_debug",
    "stop_debug",
    "restart_debug",
    # Breakpoint management
    "set_breakpoint",
    "remove_breakpoint",
    "list_breakpoints",
    "enable_breakpoint",
    "disable_breakpoint",
    # Execution control
    "continue_execution",
    "step",
    "next_line",
    "return_from_function",
    "until",
    # Stack navigation
    "where",
    "backtrace",
    "up",
    "down",
    # Inspection
    "list_source",
    "inspect_variable",
    "list_variables",
    "evaluate",
]
