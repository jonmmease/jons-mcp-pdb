# Modernize jons-mcp-pdb

## Overview

Modernize the jons-mcp-pdb MCP server to follow the patterns and best practices established in jons-mcp-rust-analyzer. The goal is to improve code organization, maintainability, and align with modern Python packaging standards using uv.

## Current State

The jons-mcp-pdb server is a functional MCP server for Python debugging with:
- Single large file (`src/jons_mcp_pdb.py` - 1,376 lines)
- Basic pyproject.toml configuration
- Uses pixi references in some places (should be uv only)
- Missing type safety (no mypy configuration)
- Tests exist but need organization improvements
- Missing CLAUDE.md development guide

## Target Architecture

Following jons-mcp-rust-analyzer patterns:

```
src/
├── __init__.py
└── jons_mcp_pdb/
    ├── __init__.py           # Package exports and version
    ├── constants.py          # Timeouts, defaults, state enums
    ├── exceptions.py         # Custom exception classes
    ├── utils.py              # Helper functions (pagination, parsing)
    ├── pdb_client.py         # PdbClient class (subprocess management)
    ├── server.py             # FastMCP server setup and lifespan
    └── tools/
        ├── __init__.py       # Tool re-exports
        ├── session.py        # Session management tools
        ├── breakpoints.py    # Breakpoint tools
        ├── execution.py      # Execution control tools
        ├── navigation.py     # Stack navigation tools
        └── inspection.py     # Variable/source inspection tools
tests/
├── conftest.py               # Shared fixtures
├── test_pdb_client.py        # PdbClient unit tests
├── test_mcp_tools.py         # MCP tool function tests
└── test_integration.py       # Full integration tests
```

## Key Changes

### 1. Package Restructuring
- Move from flat `src/jons_mcp_pdb.py` to proper package structure
- Split monolithic file into focused modules
- Organize tools by category (session, breakpoints, execution, navigation, inspection)

### 2. pyproject.toml Modernization
- Update entry point to new package structure
- Add mypy configuration with strict type checking
- Ensure pytest-asyncio configuration matches reference
- Add proper optional-dependencies groups
- Configure `[tool.uv]` for dev dependencies

### 3. Code Quality
- Add type hints to all functions
- Create custom exception classes
- Extract constants to dedicated module
- Create utility functions module

### 4. Testing Improvements
- Add conftest.py with shared fixtures
- Reorganize tests to match new module structure
- Add integration test markers
- Move test samples to tests/samples/

### 5. Documentation
- Create CLAUDE.md with development commands and architecture
- Update README.md with uv-focused instructions
- Remove pixi references, use uv exclusively

### 6. Server Architecture
- Use FastMCP lifespan context manager pattern
- Proper async/await patterns where applicable
- Signal handling for graceful shutdown
- Module-level state with clear documentation

## Implementation Notes

- Preserve all existing functionality
- Maintain backward compatibility for MCP tool signatures
- Keep the subprocess-based pdb architecture
- Retain pagination support across all list operations
- Configuration loading (pdbconfig.json) should continue to work
