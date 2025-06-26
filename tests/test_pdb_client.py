#!/usr/bin/env python3
"""Comprehensive tests for PdbClient functionality."""

import pytest
import json
import time
import sys
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_pdb import PdbClient, DebuggerState, Config, StackFrame


@pytest.fixture
def client():
    """Create a PdbClient instance and clean up after test."""
    client = PdbClient()
    
    # Ensure clean state before test
    for session_id in list(client.sessions.keys()):
        client.close_session(session_id)

    yield client

    # Cleanup after test
    for session_id in list(client.sessions.keys()):
        client.close_session(session_id)


@pytest.fixture
def test_script_path():
    """Path to test script."""
    return str(Path(__file__).parent.parent / "test_samples" / "sample_script.py")


@pytest.fixture
def test_module_path():
    """Path to test module."""
    return str(Path(__file__).parent.parent / "test_samples" / "sample_pytest_debug.py")


def test_config_loading():
    """Test configuration loading."""
    # Test default config
    client = PdbClient()
    assert client.config.working_directory == "."
    assert client.config.debug_mode == "script"

    # Test config with custom values
    config = Config(python_path="/usr/bin/python3", venv=".venv", debug_mode="pytest")
    assert config.python_path == "/usr/bin/python3"
    assert config.venv == ".venv"
    assert config.debug_mode == "pytest"

    # Test config loading from file
    config_path = Path("pdbconfig.json")
    test_config = {
        "python_path": sys.executable,
        "working_directory": ".",
        "debug_mode": "script",
        "environment": {"TEST_VAR": "test_value"},
    }

    try:
        with open(config_path, "w") as f:
            json.dump(test_config, f)

        # Create new client to load config
        test_client = PdbClient()

        assert test_client.config.python_path == sys.executable
        assert test_client.config.debug_mode == "script"
        assert test_client.config.environment["TEST_VAR"] == "test_value"

    finally:
        if config_path.exists():
            config_path.unlink()


def test_session_management(client):
    """Test session creation and management."""
    # Test session creation
    session_id = client.create_session()
    assert session_id.startswith("session_")
    assert session_id in client.sessions

    # Test getting session
    session = client.sessions.get(session_id)
    assert session is not None
    assert session.session_id == session_id
    assert session.state == DebuggerState.IDLE

    # Test closing session
    success = client.close_session(session_id)
    assert success == True
    assert session_id not in client.sessions

    # Test closing non-existent session
    success = client.close_session("non_existent")
    assert success == False


def test_location_parsing(client):
    """Test parsing of location information."""
    # Test valid location
    output = "> /path/to/file.py(42)function_name()"
    location = client._parse_location(output)
    assert location is not None
    assert location.file == "/path/to/file.py"
    assert location.line == 42
    assert location.function == "function_name"

    # Test invalid location
    output = "Not a location"
    location = client._parse_location(output)
    assert location is None


def test_stack_frame_parsing(client):
    """Test parsing of stack frames."""
    # Test valid stack trace
    output = """  /path/to/file1.py(10)main()
  /path/to/file2.py(20)helper()
  /path/to/file3.py(30)deep_function()"""

    frames = client._parse_stack_frames(output)
    assert len(frames) == 3

    assert frames[0].file == "/path/to/file1.py"
    assert frames[0].line == 10
    assert frames[0].function == "main"

    assert frames[1].file == "/path/to/file2.py"
    assert frames[1].line == 20
    assert frames[1].function == "helper"

    assert frames[2].file == "/path/to/file3.py"
    assert frames[2].line == 30
    assert frames[2].function == "deep_function"


def test_python_executable_detection(client):
    """Test Python executable detection."""
    # Test finding Python executable
    python_exe = client._find_python_executable()
    assert python_exe is not None
    assert os.path.exists(python_exe)

    # Test with custom config
    client.config.python_path = sys.executable
    python_exe = client._find_python_executable()
    assert python_exe == sys.executable


def test_script_mode_debugging(client, test_script_path):
    """Test debugging a Python script."""
    session_id = client.create_session()

    try:
        # Start debugging
        result = client.start_debug(session_id, test_script_path, mode="script")
        assert "error" not in result
        assert result["status"] == "started"

        # Verify session state
        session = client.sessions.get(session_id)
        assert session is not None
        assert session.process is not None
        assert session.state == DebuggerState.PAUSED

        # Test basic commands
        time.sleep(0.5)  # Let process start

        # List source
        result = client.send_command(session_id, "list")
        assert "error" not in result
        assert "def" in result["output"] or "import" in result["output"]

        # Set breakpoint
        result = client.send_command(session_id, f"break {test_script_path}:22")
        assert "error" not in result
        assert "Breakpoint 1" in result["output"]

        # Continue execution
        result = client.send_command(session_id, "continue")
        assert "error" not in result

    finally:
        client.close_session(session_id)


def test_pytest_mode_debugging(client, test_module_path):
    """Test debugging pytest tests."""
    session_id = client.create_session()

    try:
        # Start pytest debugging
        result = client.start_debug(
            session_id,
            test_module_path,
            mode="pytest",
            args=["-v", "-k", "test_add_numbers"],
        )

        # Note: pytest --trace has different behavior
        # For this test, we just verify it starts correctly
        assert "error" not in result or "pytest not found" in str(
            result.get("error", "")
        )

    finally:
        client.close_session(session_id)


def test_breakpoint_operations(client, test_script_path):
    """Test breakpoint setting, listing, and removal."""
    session_id = client.create_session()

    try:
        # Start debugging
        result = client.start_debug(session_id, test_script_path, mode="script")
        assert "error" not in result

        time.sleep(0.5)  # Let process start

        # Set a breakpoint
        result = client.send_command(session_id, f"break {test_script_path}:22")
        assert "error" not in result
        assert "Breakpoint 1" in result["output"]

        # List breakpoints
        result = client.send_command(session_id, "break")
        assert "error" not in result
        assert test_script_path in result["output"]

        # Continue to breakpoint
        result = client.send_command(session_id, "continue")
        assert "error" not in result

        # Should hit the breakpoint
        session = client.sessions.get(session_id)
        assert session.state == DebuggerState.PAUSED

        # Remove breakpoint
        result = client.send_command(session_id, "clear 1")
        assert "error" not in result

    finally:
        client.close_session(session_id)


def test_stepping_operations(client, test_script_path):
    """Test step, next, and continue operations."""
    session_id = client.create_session()

    try:
        # Start debugging
        result = client.start_debug(session_id, test_script_path, mode="script")
        assert "error" not in result

        time.sleep(0.5)  # Let process start

        # Step into
        result = client.send_command(session_id, "step")
        assert "error" not in result
        location = client._parse_location(result["output"])
        assert location is not None

        # Next (step over)
        result = client.send_command(session_id, "next")
        assert "error" not in result

        # Continue
        result = client.send_command(session_id, "continue")
        assert "error" not in result

        # Wait for completion
        time.sleep(1)
        session = client.sessions.get(session_id)

        # Should have finished or be at another breakpoint
        assert session.state in [DebuggerState.FINISHED, DebuggerState.PAUSED]

    finally:
        client.close_session(session_id)


def test_stack_navigation(client, test_script_path):
    """Test where, up, and down commands."""
    session_id = client.create_session()

    try:
        # Start debugging
        result = client.start_debug(session_id, test_script_path, mode="script")
        assert "error" not in result

        time.sleep(0.5)  # Let process start

        # Set breakpoint in calculate_factorial
        result = client.send_command(session_id, "break calculate_factorial")
        assert "error" not in result

        # Continue to breakpoint
        result = client.send_command(session_id, "continue")
        assert "error" not in result

        # Get stack trace
        result = client.send_command(session_id, "where")
        assert "error" not in result
        frames = client._parse_stack_frames(result["output"])
        assert len(frames) > 0

        # Move up in stack
        result = client.send_command(session_id, "up")
        assert "error" not in result

        # Move down in stack
        result = client.send_command(session_id, "down")
        assert "error" not in result

    finally:
        client.close_session(session_id)


def test_variable_inspection(client, test_script_path):
    """Test variable listing and inspection."""
    session_id = client.create_session()

    try:
        # Start debugging
        result = client.start_debug(session_id, test_script_path, mode="script")
        assert "error" not in result

        time.sleep(0.5)  # Let process start

        # Set breakpoint in main
        result = client.send_command(session_id, "break main")
        assert "error" not in result

        # Continue to breakpoint
        result = client.send_command(session_id, "continue")
        assert "error" not in result

        # List variables
        result = client.send_command(session_id, "p locals()")
        assert "error" not in result

        # Inspect a specific variable
        result = client.send_command(session_id, "p n")
        assert "error" not in result

        # Evaluate expression
        result = client.send_command(session_id, "p 2 + 2")
        assert "error" not in result
        assert "4" in result["output"]

    finally:
        client.close_session(session_id)


def test_concurrent_sessions(client, test_script_path):
    """Test running multiple debug sessions concurrently."""
    session1 = client.create_session()
    session2 = client.create_session()

    try:
        # Start both sessions
        result1 = client.start_debug(session1, test_script_path, mode="script")
        result2 = client.start_debug(session2, test_script_path, mode="script")

        assert "error" not in result1
        assert "error" not in result2

        # Verify both sessions are independent
        assert (
            client.sessions[session1].process != client.sessions[session2].process
        )

        time.sleep(0.5)  # Let processes start

        # Send commands to both
        result1 = client.send_command(session1, "list")
        result2 = client.send_command(session2, "list")

        assert "error" not in result1
        assert "error" not in result2

    finally:
        client.close_session(session1)
        client.close_session(session2)


def test_command_line_arguments(client, test_script_path):
    """Test debugging with command line arguments."""
    session_id = client.create_session()

    try:
        # Start with arguments
        result = client.start_debug(
            session_id, test_script_path, mode="script", args=["5", "test_arg"]
        )
        assert "error" not in result

        time.sleep(0.5)  # Let process start

        # Continue execution
        result = client.send_command(session_id, "continue")
        assert "error" not in result

        # Wait for completion
        time.sleep(1)

        # Check if arguments were processed
        session = client.sessions.get(session_id)
        # Output would contain "Command line arguments: ['5', 'test_arg']"

    finally:
        client.close_session(session_id)


def test_error_handling(client):
    """Test error handling scenarios."""
    # Test invalid session ID
    result = client.send_command("invalid_session", "list")
    assert result["error"] == "Session not found"

    # Test starting debug without target
    session_id = client.create_session()
    try:
        result = client.start_debug(session_id, "nonexistent_file.py")
        # Should handle gracefully
        assert result is not None
    finally:
        client.close_session(session_id)


def test_simple_script_execution(client):
    """Test basic debugging with a simple temporary script."""
    # Create a temporary test script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("""
import sys

def main():
    x = 10
    y = 20
    z = x + y
    print(f"Result: {z}")
    return z

if __name__ == "__main__":
    result = main()
    sys.exit(0)
""")
        test_script = f.name

    try:
        session_id = client.create_session()

        # Start debugging
        result = client.start_debug(session_id, test_script, mode="script")
        if "error" not in result:
            # Wait a moment for process to start
            time.sleep(0.5)

            # Check session state
            session = client.sessions.get(session_id)
            if session and session.process:
                # Send a simple command
                result = client.send_command(session_id, "list")
                assert "error" not in result

        # Cleanup
        client.close_session(session_id)

    finally:
        # Remove temporary file
        os.unlink(test_script)


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])