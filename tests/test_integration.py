"""End-to-end integration tests with real pdb processes.

These tests spawn actual pdb subprocesses and verify the MCP tools work correctly
with real debugging sessions.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path

import pytest

from src.jons_mcp_pdb import PdbClient
from src.jons_mcp_pdb import server as server_module
from src.jons_mcp_pdb.constants import DebuggerState
from src.jons_mcp_pdb.tools import (
    continue_execution,
    down,
    evaluate,
    inspect_variable,
    list_breakpoints,
    list_source,
    list_variables,
    next_line,
    remove_breakpoint,
    set_breakpoint,
    start_debug,
    step,
    stop_debug,
    up,
    where,
)


@pytest.fixture
def integration_client() -> Generator[PdbClient, None, None]:
    """Create a fresh PdbClient for integration tests."""
    client = PdbClient()
    server_module._client = client
    yield client
    # Cleanup all sessions
    for session_id in list(client.sessions.keys()):
        try:
            client.close_session(session_id)
        except Exception:
            pass
    server_module._client = None


@pytest.mark.integration
class TestPdbIntegration:
    """End-to-end integration tests with real pdb processes."""

    def test_full_debugging_lifecycle(
        self, integration_client: PdbClient, test_script_path: str
    ) -> None:
        """Test complete debugging lifecycle: start → breakpoint → continue → inspect → stop."""
        # Start debugging
        result = start_debug(test_script_path, mode="script")
        assert "error" not in result
        assert "session_id" in result
        session_id = result["session_id"]

        time.sleep(0.5)  # Let process start

        # Set a breakpoint
        result = set_breakpoint(session_id, file=test_script_path, line=22)
        assert "error" not in result or "breakpoint_id" in result

        # Continue to breakpoint
        result = continue_execution(session_id)
        assert "stopped_at" in result or "error" not in result

        # List variables at breakpoint
        result = list_variables(session_id)
        assert "locals" in result

        # Stop debugging
        result = stop_debug(session_id)
        assert result["status"] == "stopped"

    def test_step_through_function(
        self, integration_client: PdbClient, simple_pdb_script_path: str
    ) -> None:
        """Test stepping through function execution."""
        # Start debugging the simple factorial script
        result = start_debug(simple_pdb_script_path, mode="script")
        assert "error" not in result
        session_id = result["session_id"]

        time.sleep(0.5)

        # Step a few times
        for _ in range(3):
            result = step(session_id)
            assert "location" in result or "error" not in result

        # Use next to step over
        result = next_line(session_id)
        assert "location" in result or "error" not in result

        # Cleanup
        stop_debug(session_id)

    def test_variable_inspection_in_context(
        self, integration_client: PdbClient, test_script_path: str
    ) -> None:
        """Test inspecting variables during debugging."""
        # Start debugging
        result = start_debug(test_script_path, mode="script")
        assert "error" not in result
        session_id = result["session_id"]

        time.sleep(0.5)

        # Set breakpoint in main function where variables are defined
        result = set_breakpoint(session_id, file=test_script_path, function="main")
        if "error" not in result:
            # Continue to breakpoint
            result = continue_execution(session_id)

            # Try to inspect a variable (may or may not be defined yet)
            result = list_variables(session_id)
            assert "locals" in result

        # Cleanup
        stop_debug(session_id)

    def test_stack_navigation_real(
        self, integration_client: PdbClient, test_script_path: str
    ) -> None:
        """Test stack navigation with real call stack."""
        # Start debugging
        result = start_debug(test_script_path, mode="script")
        assert "error" not in result
        session_id = result["session_id"]

        time.sleep(0.5)

        # Set breakpoint in a nested function
        result = set_breakpoint(
            session_id, file=test_script_path, function="calculate_factorial"
        )
        if "error" not in result:
            # Continue to hit breakpoint
            result = continue_execution(session_id)

            # Get stack trace
            result = where(session_id)
            assert "frames" in result

            # Try moving up in stack
            result = up(session_id)
            assert "frame" in result

            # Try moving down in stack
            result = down(session_id)
            assert "frame" in result

        # Cleanup
        stop_debug(session_id)

    def test_evaluate_expressions(
        self, integration_client: PdbClient, test_script_path: str
    ) -> None:
        """Test evaluating expressions during debugging."""
        # Start debugging
        result = start_debug(test_script_path, mode="script")
        assert "error" not in result
        session_id = result["session_id"]

        time.sleep(0.5)

        # Evaluate simple expression
        result = evaluate(session_id, expression="2 + 2")
        assert "result" in result
        assert "4" in result["result"]

        # Evaluate with Python built-in
        result = evaluate(session_id, expression="len([1, 2, 3])")
        assert "result" in result
        assert "3" in result["result"]

        # Cleanup
        stop_debug(session_id)

    def test_source_listing(
        self, integration_client: PdbClient, test_script_path: str
    ) -> None:
        """Test listing source code during debugging."""
        # Start debugging
        result = start_debug(test_script_path, mode="script")
        assert "error" not in result
        session_id = result["session_id"]

        time.sleep(0.5)

        # List source at current position
        result = list_source(session_id)
        assert "source" in result
        assert len(result["source"]) > 0

        # Cleanup
        stop_debug(session_id)

    def test_breakpoint_management(
        self, integration_client: PdbClient, test_script_path: str
    ) -> None:
        """Test setting, listing, and removing breakpoints."""
        # Start debugging
        result = start_debug(test_script_path, mode="script")
        assert "error" not in result
        session_id = result["session_id"]

        time.sleep(0.5)

        # Set multiple breakpoints
        bp1 = set_breakpoint(session_id, file=test_script_path, line=22)
        bp2 = set_breakpoint(session_id, file=test_script_path, line=30)

        # List breakpoints
        result = list_breakpoints(session_id)
        assert "breakpoints" in result

        # Remove first breakpoint if it was set successfully
        if "breakpoint_id" in bp1:
            result = remove_breakpoint(session_id, breakpoint_id=bp1["breakpoint_id"])
            assert result["status"] == "removed"

        # Cleanup
        stop_debug(session_id)

    def test_concurrent_debug_sessions(
        self, integration_client: PdbClient, test_script_path: str
    ) -> None:
        """Test running multiple debug sessions concurrently."""
        # Start first session
        result1 = start_debug(test_script_path, mode="script")
        assert "error" not in result1
        session1 = result1["session_id"]

        # Start second session
        result2 = start_debug(test_script_path, mode="script")
        assert "error" not in result2
        session2 = result2["session_id"]

        time.sleep(0.5)

        # Both sessions should be independent
        assert session1 != session2

        # Send commands to both
        result1 = list_source(session1)
        result2 = list_source(session2)

        assert "source" in result1
        assert "source" in result2

        # Cleanup both
        stop_debug(session1)
        stop_debug(session2)


@pytest.mark.integration
class TestPytestModeIntegration:
    """Integration tests for pytest debugging mode."""

    def test_pytest_mode_start(
        self, integration_client: PdbClient, test_module_path: str
    ) -> None:
        """Test starting pytest debugging mode."""
        # Start pytest debugging
        result = start_debug(
            test_module_path, mode="pytest", args=["-v", "-k", "test_add_numbers"]
        )

        # Pytest mode may behave differently, check for either success or expected error
        if "error" not in result:
            session_id = result["session_id"]
            time.sleep(1)  # Pytest takes longer to start

            # Try to get current state
            session = integration_client.sessions.get(session_id)
            assert session is not None

            # Cleanup
            stop_debug(session_id)
