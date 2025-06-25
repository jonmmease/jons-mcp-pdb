#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "fastmcp>=0.2.8",
# ]
# ///

"""Simple test for MCP PDB server - runs server and tests it"""

import json
import asyncio
import sys
from mcp.server.fastmcp import FastMCP

# Import the tools from pdb_mcp by executing it in a special way
import importlib.util
spec = importlib.util.spec_from_file_location("pdb_mcp", "pdb_mcp.py")
pdb_mcp = importlib.util.module_from_spec(spec)
sys.modules["pdb_mcp"] = pdb_mcp
spec.loader.exec_module(pdb_mcp)

async def test_debugging():
    """Test the debugging functionality"""
    print("=== Testing MCP PDB Server ===\n")
    
    # Test 1: Create session
    print("1. Creating session...")
    result = pdb_mcp.create_session()
    print(f"   Result: {result}")
    session_id = result["session_id"]
    
    # Test 2: Run code without breakpoints (should not hang)
    print("\n2. Running code without breakpoints...")
    result = pdb_mcp.run_code(
        session_id=session_id,
        code='print("Hello from debugger!\\nx = 5\\nprint(f\\"x = {x}\\")")'
    )
    print(f"   Result: {result}")
    
    # Wait a moment for execution
    await asyncio.sleep(0.5)
    
    # Test 3: Check state
    print("\n3. Checking session state...")
    result = pdb_mcp.get_session_state(session_id)
    print(f"   State: {result.get('state')}")
    print(f"   Output: {result.get('output', '').strip()}")
    
    # Test 4: Close session
    print("\n4. Closing session...")
    result = pdb_mcp.close_session(session_id)
    print(f"   Result: {result}")
    
    # Test 5: Create new session with breakpoint
    print("\n5. Testing with breakpoint...")
    result = pdb_mcp.create_session()
    session_id = result["session_id"]
    print(f"   New session: {session_id}")
    
    # Set a breakpoint
    print("\n6. Setting breakpoint on test_pdb.py line 6...")
    result = pdb_mcp.set_breakpoint(
        session_id=session_id,
        filename="test_pdb.py",
        line=6
    )
    print(f"   Result: {result}")
    
    # Run the script
    print("\n7. Running test_pdb.py with breakpoint...")
    result = pdb_mcp.run_script(
        session_id=session_id,
        script_path="test_pdb.py"
    )
    print(f"   Result: {result}")
    
    # Wait and check state
    await asyncio.sleep(0.5)
    result = pdb_mcp.get_session_state(session_id)
    print(f"   State after run: {result.get('state')}")
    if result.get('state') == 'paused':
        print(f"   Paused at: {result.get('location')}")
    
    # Continue execution
    if result.get('state') == 'paused':
        print("\n8. Continuing execution...")
        result = pdb_mcp.continue_execution(session_id)
        print(f"   Result: {result.get('state')}")
    
    # Final cleanup
    print("\n9. Final cleanup...")
    pdb_mcp.close_session(session_id)
    print("   Session closed")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    # Run the async test
    asyncio.run(test_debugging())