#!/usr/bin/env python3
"""Sample pytest tests for debugging with MCP PDB server"""

import pytest


def add_numbers(a, b):
    """Simple function to add two numbers"""
    result = a + b
    return result


def divide_numbers(a, b):
    """Function that might raise an exception"""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


def factorial(n):
    """Calculate factorial recursively"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)


class Calculator:
    """Simple calculator class"""
    
    def __init__(self):
        self.history = []
    
    def add(self, a, b):
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def multiply(self, a, b):
        result = a * b
        self.history.append(f"{a} * {b} = {result}")
        return result


# Test functions

def test_add_numbers():
    """Test the add_numbers function"""
    result = add_numbers(2, 3)
    assert result == 5
    
    result = add_numbers(-1, 1)
    assert result == 0


def test_divide_numbers():
    """Test the divide_numbers function"""
    result = divide_numbers(10, 2)
    assert result == 5.0
    
    result = divide_numbers(7, 3)
    assert abs(result - 2.333333) < 0.001


def test_divide_by_zero():
    """Test that division by zero raises an exception"""
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide_numbers(5, 0)


def test_factorial():
    """Test factorial calculation"""
    assert factorial(0) == 1
    assert factorial(1) == 1
    assert factorial(5) == 120
    
    # This test will help demonstrate recursive debugging
    result = factorial(4)
    assert result == 24


def test_calculator_class():
    """Test the Calculator class"""
    calc = Calculator()
    
    # Test addition
    result = calc.add(3, 4)
    assert result == 7
    assert len(calc.history) == 1
    
    # Test multiplication
    result = calc.multiply(5, 6)
    assert result == 30
    assert len(calc.history) == 2
    
    # Check history
    assert "3 + 4 = 7" in calc.history
    assert "5 * 6 = 30" in calc.history


def test_complex_calculation():
    """Test a more complex calculation for debugging"""
    numbers = [1, 2, 3, 4, 5]
    
    # Calculate sum of squares
    squares = []
    for num in numbers:
        square = num * num
        squares.append(square)
    
    total = sum(squares)
    expected = 1 + 4 + 9 + 16 + 25  # 55
    
    assert total == expected


@pytest.mark.parametrize("a,b,expected", [
    (1, 2, 3),
    (0, 0, 0),
    (-1, 1, 0),
    (10, -5, 5),
])
def test_add_parametrized(a, b, expected):
    """Parametrized test for addition"""
    result = add_numbers(a, b)
    assert result == expected


def test_failing_test():
    """This test is designed to fail for debugging purposes"""
    # Uncomment the line below to make this test fail
    # assert False, "This test is meant to fail for debugging"
    pass
