"""Shared pytest fixtures for jons-mcp-pdb tests."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.jons_mcp_pdb import Breakpoint, DebugSession, PdbClient, StackFrame
from src.jons_mcp_pdb import server as server_module
from src.jons_mcp_pdb.constants import DebuggerState


@pytest.fixture
def client() -> Generator[PdbClient, None, None]:
    """Create a PdbClient instance and clean up after test."""
    pdb_client = PdbClient()

    # Ensure clean state before test
    for session_id in list(pdb_client.sessions.keys()):
        pdb_client.close_session(session_id)

    yield pdb_client

    # Cleanup after test
    for session_id in list(pdb_client.sessions.keys()):
        pdb_client.close_session(session_id)


@pytest.fixture(autouse=True)
def reset_globals() -> Generator[None, None, None]:
    """Reset global state between tests."""
    # Save original state
    original_client = server_module._client

    yield

    # Restore original state
    server_module._client = original_client


@pytest.fixture
def test_script_path() -> str:
    """Path to test script."""
    return str(Path(__file__).parent / "samples" / "sample_script.py")


@pytest.fixture
def test_module_path() -> str:
    """Path to test module."""
    return str(Path(__file__).parent / "samples" / "sample_pytest_debug.py")


@pytest.fixture
def simple_pdb_script_path() -> str:
    """Path to simple pdb test script."""
    return str(Path(__file__).parent / "samples" / "sample_pdb.py")


@pytest.fixture
def mock_pdb_client() -> MagicMock:
    """Create a mock PdbClient with configured return values."""
    mock = MagicMock(spec=PdbClient)

    # Configure default session behavior
    mock.create_session.return_value = "session_test_123"
    mock.close_session.return_value = True

    # Configure default command responses
    mock.send_command.return_value = {"output": "", "state": "paused"}

    # Configure sessions dict
    mock.sessions = {}

    return mock


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock DebugSession with default state."""
    mock = MagicMock(spec=DebugSession)
    mock.session_id = "session_test_123"
    mock.state = DebuggerState.PAUSED
    mock.target = "/path/to/script.py"
    mock.target_type = "script"
    mock.args = []
    mock.breakpoints = {}
    mock.current_frame = StackFrame(
        index=0,
        file="/path/to/script.py",
        line=10,
        function="main",
        code="x = 1",
    )
    return mock


@pytest.fixture
def mock_pdb_output() -> dict[str, Any]:
    """Sample pdb output strings for testing parsers."""
    return {
        # Location output from pdb
        "location": "> /path/to/script.py(42)test_function()\n-> x = 1",
        # Stack trace output from 'where' command
        "stack_trace": """  /path/to/file1.py(10)main()
-> result = helper()
  /path/to/file2.py(20)helper()
-> value = deep_function()
> /path/to/file3.py(30)deep_function()
-> x = 1""",
        # Breakpoint set confirmation
        "breakpoint_set": "Breakpoint 1 at /path/to/script.py:42",
        # Breakpoint list output
        "breakpoint_list": """Num Type         Disp Enb   Where
1   breakpoint   keep yes   at /path/to/script.py:42
2   breakpoint   keep no    at /path/to/script.py:50
	stop only if x > 10""",
        # Source listing
        "source_listing": """  1  	def main():
  2  	    x = 10
  3  ->	    y = 20
  4  	    z = x + y
  5  	    return z""",
        # Variable print output
        "variable_print": "42",
        # Locals output
        "locals_output": "{'x': 10, 'y': 20, 'self': <__main__.Test object>}",
        # Return value output
        "return_output": "--Return--\n> /path/to/script.py(10)main()->42",
        # Step into function
        "step_into": "> /path/to/module.py(5)helper()\n-> return x + y",
    }


@pytest.fixture
def sample_breakpoints() -> list[Breakpoint]:
    """Create sample breakpoints for testing."""
    return [
        Breakpoint(
            id=1,
            file="/path/to/script.py",
            line=42,
            function="main",
            enabled=True,
            hit_count=0,
        ),
        Breakpoint(
            id=2,
            file="/path/to/script.py",
            line=50,
            function="helper",
            condition="x > 10",
            enabled=False,
            hit_count=3,
        ),
        Breakpoint(
            id=3,
            file="/path/to/other.py",
            line=15,
            function=None,
            temporary=True,
            enabled=True,
            hit_count=0,
        ),
    ]


@pytest.fixture
def sample_stack_frames() -> list[StackFrame]:
    """Create sample stack frames for testing."""
    return [
        StackFrame(
            index=0,
            file="/path/to/file3.py",
            line=30,
            function="deep_function",
            code="x = 1",
        ),
        StackFrame(
            index=1,
            file="/path/to/file2.py",
            line=20,
            function="helper",
            code="value = deep_function()",
        ),
        StackFrame(
            index=2,
            file="/path/to/file1.py",
            line=10,
            function="main",
            code="result = helper()",
        ),
    ]
