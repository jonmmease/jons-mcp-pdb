"""Shared pytest fixtures for jons-mcp-pdb tests."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.jons_mcp_pdb import PdbClient
from src.jons_mcp_pdb import server as server_module


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
