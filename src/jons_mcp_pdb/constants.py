"""Constants, enums, and configuration defaults for jons-mcp-pdb."""

import re
from enum import Enum

# PDB prompts and patterns
PDB_PROMPT = "(Pdb) "
PDB_PROMPT_PATTERN = re.compile(r"\(Pdb\)\s*$", re.MULTILINE)

# Breakpoint patterns
BREAKPOINT_SET_PATTERN = re.compile(r"Breakpoint (\d+) at (.+):(\d+)")
BREAKPOINT_HIT_PATTERN = re.compile(r"Breakpoint (\d+), .+ at (.+):(\d+)")

# Location patterns
CURRENT_LOCATION_PATTERN = re.compile(r"> (.+)\((\d+)\)(.+)\(\)")
STACK_FRAME_PATTERN = re.compile(r"^\s*(.+)\((\d+)\)(.+)\(\)$", re.MULTILINE)

# Timeouts (in seconds)
DEFAULT_TIMEOUT = 5.0
STARTUP_TIMEOUT = 10.0
PROCESS_TERMINATE_TIMEOUT = 5.0

# Pagination defaults
DEFAULT_PAGINATION_LIMIT = 20
DEFAULT_PAGINATION_OFFSET = 0

# Queue timeouts
QUEUE_TIMEOUT = 0.1


class DebuggerState(Enum):
    """States of the debugger."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"
