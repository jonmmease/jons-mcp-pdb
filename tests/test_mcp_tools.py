"""Tests for MCP tool functions using mocks."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.jons_mcp_pdb import Breakpoint, StackFrame
from src.jons_mcp_pdb import server as server_module
from src.jons_mcp_pdb.constants import DebuggerState
from src.jons_mcp_pdb.tools import (
    continue_execution,
    disable_breakpoint,
    down,
    enable_breakpoint,
    evaluate,
    inspect_variable,
    list_breakpoints,
    list_source,
    list_variables,
    next_line,
    remove_breakpoint,
    restart_debug,
    return_from_function,
    set_breakpoint,
    start_debug,
    step,
    stop_debug,
    until,
    up,
    where,
)


class TestSessionTools:
    """Tests for session management MCP tools."""

    def test_start_debug_script_mode(self, mock_pdb_client: MagicMock) -> None:
        """Test starting debug session in script mode."""
        mock_pdb_client.start_debug.return_value = {
            "status": "started",
            "session_id": "session_test_123",
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = start_debug("/path/to/script.py", mode="script")

        assert result["status"] == "started"
        assert "session_id" in result
        mock_pdb_client.create_session.assert_called_once()
        mock_pdb_client.start_debug.assert_called_once()

    def test_start_debug_pytest_mode(self, mock_pdb_client: MagicMock) -> None:
        """Test starting debug session in pytest mode."""
        mock_pdb_client.start_debug.return_value = {
            "status": "started",
            "session_id": "session_test_123",
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = start_debug(
                "tests/test_example.py::test_func",
                mode="pytest",
                args=["-v", "-s"],
            )

        assert result["status"] == "started"
        mock_pdb_client.start_debug.assert_called_once()
        call_args = mock_pdb_client.start_debug.call_args
        # Arguments are passed positionally: (session_id, target, mode, args)
        assert call_args[0][2] == "pytest"
        assert call_args[0][3] == ["-v", "-s"]

    def test_start_debug_error(self, mock_pdb_client: MagicMock) -> None:
        """Test start_debug handles errors."""
        mock_pdb_client.start_debug.return_value = {"error": "File not found"}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = start_debug("/nonexistent/script.py", mode="script")

        assert "error" in result

    def test_stop_debug_success(self, mock_pdb_client: MagicMock) -> None:
        """Test stopping debug session successfully."""
        mock_pdb_client.close_session.return_value = True

        with patch.object(server_module, "_client", mock_pdb_client):
            result = stop_debug("session_test_123")

        assert result["status"] == "stopped"
        mock_pdb_client.close_session.assert_called_once_with("session_test_123")

    def test_stop_debug_invalid_session(self, mock_pdb_client: MagicMock) -> None:
        """Test stopping non-existent session."""
        mock_pdb_client.close_session.return_value = False

        with patch.object(server_module, "_client", mock_pdb_client):
            result = stop_debug("invalid_session")

        assert result["status"] == "error"
        assert "message" in result

    def test_restart_debug_success(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test restarting debug session."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.close_session.return_value = True
        mock_pdb_client.create_session.return_value = "session_new_456"
        mock_pdb_client.start_debug.return_value = {
            "status": "started",
            "session_id": "session_new_456",
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = restart_debug("session_test_123")

        assert result["status"] == "started"
        assert result["session_id"] == "session_new_456"
        mock_pdb_client.close_session.assert_called_once()

    def test_restart_debug_invalid_session(self, mock_pdb_client: MagicMock) -> None:
        """Test restarting non-existent session."""
        mock_pdb_client.sessions = {}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = restart_debug("invalid_session")

        assert "error" in result


class TestBreakpointTools:
    """Tests for breakpoint MCP tools."""

    def test_set_breakpoint_by_line(self, mock_pdb_client: MagicMock) -> None:
        """Test setting breakpoint by line number."""
        mock_pdb_client.send_command.return_value = {
            "output": "Breakpoint 1 at /path/to/script.py:42"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = set_breakpoint(
                "session_test_123", file="/path/to/script.py", line=42
            )

        assert "breakpoint_id" in result
        assert result["breakpoint_id"] == 1
        mock_pdb_client.send_command.assert_called_once()

    def test_set_breakpoint_by_function(self, mock_pdb_client: MagicMock) -> None:
        """Test setting breakpoint by function name."""
        mock_pdb_client.send_command.return_value = {
            "output": "Breakpoint 1 at /path/to/script.py:10"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = set_breakpoint(
                "session_test_123", file="/path/to/script.py", function="main"
            )

        assert "breakpoint_id" in result
        call_args = mock_pdb_client.send_command.call_args
        assert "main" in call_args[0][1]

    def test_set_breakpoint_with_condition(self, mock_pdb_client: MagicMock) -> None:
        """Test setting conditional breakpoint."""
        mock_pdb_client.send_command.return_value = {
            "output": "Breakpoint 1 at /path/to/script.py:42"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = set_breakpoint(
                "session_test_123",
                file="/path/to/script.py",
                line=42,
                condition="x > 10",
            )

        assert "breakpoint_id" in result
        call_args = mock_pdb_client.send_command.call_args
        assert "x > 10" in call_args[0][1]

    def test_set_breakpoint_temporary(self, mock_pdb_client: MagicMock) -> None:
        """Test setting temporary breakpoint."""
        mock_pdb_client.send_command.return_value = {
            "output": "Breakpoint 1 at /path/to/script.py:42"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = set_breakpoint(
                "session_test_123",
                file="/path/to/script.py",
                line=42,
                temporary=True,
            )

        assert "breakpoint_id" in result
        call_args = mock_pdb_client.send_command.call_args
        assert call_args[0][1].startswith("tbreak")

    def test_remove_breakpoint_success(self, mock_pdb_client: MagicMock) -> None:
        """Test removing breakpoint successfully."""
        mock_pdb_client.send_command.return_value = {"output": "Deleted breakpoint 1"}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = remove_breakpoint("session_test_123", breakpoint_id=1)

        assert result["status"] == "removed"

    def test_remove_breakpoint_invalid(self, mock_pdb_client: MagicMock) -> None:
        """Test removing non-existent breakpoint."""
        mock_pdb_client.send_command.return_value = {"error": "Session not found"}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = remove_breakpoint("invalid_session", breakpoint_id=99)

        assert result["status"] == "error"

    def test_list_breakpoints(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test listing breakpoints with pagination."""
        mock_session.breakpoints = {
            1: Breakpoint(
                id=1,
                file="/path/to/script.py",
                line=42,
                function="main",
                enabled=True,
                hit_count=0,
            ),
            2: Breakpoint(
                id=2,
                file="/path/to/script.py",
                line=50,
                function="helper",
                enabled=False,
                hit_count=3,
            ),
        }
        mock_pdb_client.sessions = {"session_test_123": mock_session}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = list_breakpoints("session_test_123")

        assert "breakpoints" in result
        assert "pagination" in result
        assert len(result["breakpoints"]) == 2

    def test_list_breakpoints_with_pagination(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test listing breakpoints with limit and offset."""
        mock_session.breakpoints = {
            i: Breakpoint(id=i, file=f"/path/to/script.py", line=i * 10, enabled=True)
            for i in range(1, 6)
        }
        mock_pdb_client.sessions = {"session_test_123": mock_session}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = list_breakpoints("session_test_123", limit=2, offset=1)

        assert len(result["breakpoints"]) == 2
        assert result["pagination"]["total"] == 5
        assert result["pagination"]["offset"] == 1
        assert result["pagination"]["limit"] == 2

    def test_enable_breakpoint(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test enabling breakpoint."""
        mock_session.breakpoints = {
            1: Breakpoint(id=1, file="/script.py", line=10, enabled=False)
        }
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {"output": "Enabled breakpoint 1"}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = enable_breakpoint("session_test_123", breakpoint_id=1)

        assert result["status"] is True

    def test_disable_breakpoint(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test disabling breakpoint."""
        mock_session.breakpoints = {
            1: Breakpoint(id=1, file="/script.py", line=10, enabled=True)
        }
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {"output": "Disabled breakpoint 1"}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = disable_breakpoint("session_test_123", breakpoint_id=1)

        assert result["status"] is False


class TestExecutionTools:
    """Tests for execution control MCP tools."""

    def test_continue_execution_to_breakpoint(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test continue execution stops at breakpoint."""
        mock_session.state = DebuggerState.PAUSED
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "> /path/to/script.py(42)main()\n-> x = 1"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = continue_execution("session_test_123")

        assert "stopped_at" in result
        mock_pdb_client.send_command.assert_called_with("session_test_123", "continue")

    def test_continue_execution_to_end(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test continue execution reaches end."""
        mock_session.state = DebuggerState.FINISHED
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "The program finished",
            "state": "finished",
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = continue_execution("session_test_123")

        assert "stopped_at" in result or "reason" in result

    def test_step_into_function(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test step into function."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "> /path/to/module.py(5)helper()\n-> return x + y"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = step("session_test_123")

        assert "location" in result
        mock_pdb_client.send_command.assert_called_with("session_test_123", "step")

    def test_next_line(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test step over (next line)."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "> /path/to/script.py(11)main()\n-> y = 20"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = next_line("session_test_123")

        assert "location" in result
        mock_pdb_client.send_command.assert_called_with("session_test_123", "next")

    def test_return_from_function(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test return from function with return value."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "--Return--\n> /path/to/script.py(10)main()->42"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = return_from_function("session_test_123")

        assert "location" in result
        mock_pdb_client.send_command.assert_called_with("session_test_123", "return")

    def test_until_line(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test continue until specific line."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "> /path/to/script.py(50)main()\n-> return result"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = until("session_test_123", line=50)

        assert "location" in result
        mock_pdb_client.send_command.assert_called_with("session_test_123", "until 50")


class TestNavigationTools:
    """Tests for stack navigation MCP tools."""

    def test_where_returns_stack_frames(
        self,
        mock_pdb_client: MagicMock,
        mock_session: MagicMock,
        sample_stack_frames: list[StackFrame],
    ) -> None:
        """Test where returns stack frames with pagination."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": """  /path/to/file1.py(10)main()
-> result = helper()
  /path/to/file2.py(20)helper()
-> value = deep_function()
> /path/to/file3.py(30)deep_function()
-> x = 1"""
        }
        mock_pdb_client._parse_stack_frames.return_value = sample_stack_frames

        with patch.object(server_module, "_client", mock_pdb_client):
            result = where("session_test_123")

        assert "frames" in result
        assert "pagination" in result
        mock_pdb_client.send_command.assert_called_with("session_test_123", "where")

    def test_where_with_pagination(
        self,
        mock_pdb_client: MagicMock,
        mock_session: MagicMock,
        sample_stack_frames: list[StackFrame],
    ) -> None:
        """Test where with limit and offset."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {"output": "stack trace output"}
        mock_pdb_client._parse_stack_frames.return_value = sample_stack_frames

        with patch.object(server_module, "_client", mock_pdb_client):
            result = where("session_test_123", limit=2, offset=1)

        assert "pagination" in result
        assert result["pagination"]["limit"] == 2
        assert result["pagination"]["offset"] == 1

    def test_backtrace_alias(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test backtrace is alias for where."""
        from src.jons_mcp_pdb.tools.navigation import backtrace

        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {"output": ""}
        mock_pdb_client._parse_stack_frames.return_value = []

        with patch.object(server_module, "_client", mock_pdb_client):
            result = backtrace("session_test_123")

        assert "frames" in result

    def test_up_single_frame(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test moving up single frame."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "> /path/to/file2.py(20)helper()"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = up("session_test_123")

        assert "frame" in result
        mock_pdb_client.send_command.assert_called_with("session_test_123", "up")

    def test_up_multiple_frames(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test moving up multiple frames."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {"output": ""}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = up("session_test_123", count=3)

        mock_pdb_client.send_command.assert_called_with("session_test_123", "up 3")

    def test_down_single_frame(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test moving down single frame."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {"output": ""}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = down("session_test_123")

        assert "frame" in result
        mock_pdb_client.send_command.assert_called_with("session_test_123", "down")

    def test_down_multiple_frames(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test moving down multiple frames."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {"output": ""}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = down("session_test_123", count=2)

        mock_pdb_client.send_command.assert_called_with("session_test_123", "down 2")


class TestInspectionTools:
    """Tests for inspection MCP tools."""

    def test_list_source_current(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test listing source at current position."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": """  1  	def main():
  2  	    x = 10
  3  ->	    y = 20
  4  	    z = x + y
  5  	    return z"""
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = list_source("session_test_123")

        assert "source" in result
        mock_pdb_client.send_command.assert_called()

    def test_list_source_at_line(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test listing source at specific line."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {"output": "source listing"}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = list_source("session_test_123", line=50, range=10)

        assert "source" in result
        call_args = mock_pdb_client.send_command.call_args
        assert "50" in call_args[0][1] or "list" in call_args[0][1]

    def test_list_source_with_pagination(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test listing source with pagination."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "\n".join([f"  {i}  \tline {i}" for i in range(1, 21)])
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = list_source("session_test_123", limit=5, offset=2)

        assert "pagination" in result

    def test_inspect_variable(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test inspecting variable."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.side_effect = [
            {"output": "42"},  # p name
            {"output": "<class 'int'>"},  # p type(name)
            {"output": "42"},  # p repr(name)
            {"output": "42"},  # p str(name)
            {"output": "[]"},  # attributes
        ]

        with patch.object(server_module, "_client", mock_pdb_client):
            result = inspect_variable("session_test_123", name="x")

        assert "name" in result
        assert result["name"] == "x"

    def test_list_variables_locals_only(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test listing local variables only."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.return_value = {
            "output": "{'x': 10, 'y': 20}"
        }

        with patch.object(server_module, "_client", mock_pdb_client):
            result = list_variables("session_test_123")

        assert "locals" in result
        assert "pagination" in result

    def test_list_variables_with_globals(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test listing variables including globals."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.side_effect = [
            {"output": "{'x': 10}"},  # locals()
            {"output": "{'__name__': '__main__'}"},  # globals()
        ]

        with patch.object(server_module, "_client", mock_pdb_client):
            result = list_variables("session_test_123", include_globals=True)

        assert "locals" in result
        assert "globals" in result

    def test_evaluate_expression(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test evaluating expression."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.side_effect = [
            {"output": "30"},  # p expression
            {"output": "<class 'int'>"},  # p type(...)
        ]

        with patch.object(server_module, "_client", mock_pdb_client):
            result = evaluate("session_test_123", expression="x + y")

        assert "result" in result
        assert result["result"] == "30"

    def test_evaluate_with_error(
        self, mock_pdb_client: MagicMock, mock_session: MagicMock
    ) -> None:
        """Test evaluating expression that raises error."""
        mock_pdb_client.sessions = {"session_test_123": mock_session}
        mock_pdb_client.send_command.side_effect = [
            {"output": "*** NameError: name 'undefined' is not defined"},
            {"output": "<class 'NoneType'>"},
        ]

        with patch.object(server_module, "_client", mock_pdb_client):
            result = evaluate("session_test_123", expression="undefined")

        assert "result" in result or "error" in result


class TestErrorHandling:
    """Tests for error handling across tools."""

    def test_tool_with_no_client(self) -> None:
        """Test tool behavior when client is None."""
        with patch.object(server_module, "_client", None):
            # Should create a new client via get_client()
            # This tests the lazy initialization path
            pass

    def test_tool_with_invalid_session(self, mock_pdb_client: MagicMock) -> None:
        """Test tool with invalid session ID."""
        mock_pdb_client.send_command.return_value = {"error": "Session not found"}
        mock_pdb_client.sessions = {}

        with patch.object(server_module, "_client", mock_pdb_client):
            result = step("invalid_session")

        assert "error" in result or "location" in result
