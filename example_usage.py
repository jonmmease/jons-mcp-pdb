#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "fastmcp>=0.2.8",
# ]
# ///

"""Example usage of MCP PDB server"""

import importlib.util
import sys

# Import pdb_mcp module
spec = importlib.util.spec_from_file_location("pdb_mcp", "pdb_mcp.py")
pdb_mcp = importlib.util.module_from_spec(spec)
sys.modules["pdb_mcp"] = pdb_mcp
spec.loader.exec_module(pdb_mcp)

def example_basic_debugging():
    """Example: Basic debugging workflow"""
    print("=== Example: Basic Debugging ===\n")
    
    # Create a debugging session
    session = pdb_mcp.create_session()
    session_id = session["session_id"]
    print(f"Created session: {session_id}")
    
    # Run some code
    code = """
def calculate(x, y):
    result = x + y
    print(f"{x} + {y} = {result}")
    return result

total = calculate(5, 3)
print(f"Total: {total}")
"""
    
    print("\nRunning code without breakpoints...")
    pdb_mcp.run_code(session_id, code)
    
    # Check the output
    import time
    time.sleep(0.5)
    state = pdb_mcp.get_session_state(session_id)
    print(f"State: {state['state']}")
    print(f"Output:\n{state['output']}")
    
    # Close session
    pdb_mcp.close_session(session_id)
    print("Session closed\n")

def example_with_breakpoints():
    """Example: Debugging with breakpoints"""
    print("=== Example: Debugging with Breakpoints ===\n")
    
    # Create session
    session = pdb_mcp.create_session()
    session_id = session["session_id"]
    
    # Set a breakpoint on line 6 of test_pdb.py
    bp = pdb_mcp.set_breakpoint(session_id, "test_pdb.py", line=6)
    print(f"Set breakpoint: {bp}")
    
    # Run the script
    print("\nRunning test_pdb.py...")
    pdb_mcp.run_script(session_id, "test_pdb.py")
    
    # Wait and check state
    import time
    time.sleep(0.5)
    state = pdb_mcp.get_session_state(session_id)
    print(f"\nPaused at breakpoint!")
    print(f"State: {state['state']}")
    
    # Inspect variables
    vars_info = pdb_mcp.list_variables(session_id)
    print(f"\nLocal variables: {list(vars_info.get('locals', {}).keys())}")
    
    # Step through code
    print("\nStepping...")
    pdb_mcp.step(session_id)
    
    # Continue execution
    print("\nContinuing...")
    pdb_mcp.continue_execution(session_id)
    
    # Get final output
    time.sleep(0.5)
    state = pdb_mcp.get_session_state(session_id)
    print(f"\nFinal state: {state['state']}")
    print(f"Output:\n{state['output'][:200]}...")
    
    # Close session
    pdb_mcp.close_session(session_id)
    print("\nSession closed")

def example_pytest_debugging():
    """Example: Debugging pytest"""
    print("\n=== Example: Debugging with pytest ===\n")
    
    # Create test file
    with open("test_example.py", "w") as f:
        f.write("""
def test_addition():
    x = 5
    y = 3
    assert x + y == 8
    
def test_multiplication():
    x = 4
    y = 7
    result = x * y
    assert result == 28
""")
    
    # Create session
    session = pdb_mcp.create_session()
    session_id = session["session_id"]
    
    # Run pytest module with specific test
    print("Running pytest on specific test...")
    
    # Handle args as JSON string (like LLM would send)
    args_json = '["test_example.py::test_multiplication", "-v"]'
    pdb_mcp.run_module(session_id, "pytest", args=args_json)
    
    # Check result
    import time
    time.sleep(1)
    state = pdb_mcp.get_session_state(session_id)
    print(f"\nState: {state['state']}")
    print(f"Output:\n{state['output'][:300]}...")
    
    # Cleanup
    pdb_mcp.close_session(session_id)
    import os
    os.remove("test_example.py")
    print("\nCleaned up")

if __name__ == "__main__":
    # Run examples
    example_basic_debugging()
    print("\n" + "="*50 + "\n")
    example_with_breakpoints()
    print("\n" + "="*50 + "\n")
    example_pytest_debugging()