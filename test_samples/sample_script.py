#!/usr/bin/env python3
"""Test script for debugging with MCP PDB server."""

import sys
import time


def calculate_factorial(n):
    """Calculate factorial of n recursively."""
    if n <= 1:
        return 1
    else:
        result = n * calculate_factorial(n - 1)
        return result


def process_list(items):
    """Process a list of items."""
    processed = []
    for i, item in enumerate(items):
        # Good place for a breakpoint
        squared = item**2
        processed.append({"original": item, "squared": squared, "index": i})
    return processed


def divide_numbers(a, b):
    """Divide two numbers with error handling."""
    try:
        result = a / b
        return result
    except ZeroDivisionError as e:
        print(f"Error: Cannot divide by zero - {e}")
        raise


class DataProcessor:
    """Simple class for testing object inspection."""

    def __init__(self, name):
        self.name = name
        self.data = []
        self.processed_count = 0

    def add_data(self, item):
        """Add data to the processor."""
        self.data.append(item)

    def process_all(self):
        """Process all data items."""
        results = []
        for item in self.data:
            self.processed_count += 1
            result = self._process_item(item)
            results.append(result)
        return results

    def _process_item(self, item):
        """Process a single item."""
        return item.upper() if isinstance(item, str) else str(item)


def main():
    """Main function to demonstrate various debugging scenarios."""
    print("Starting test script...")

    # Test factorial calculation
    n = 5
    fact_result = calculate_factorial(n)
    print(f"Factorial of {n} is {fact_result}")

    # Test list processing
    numbers = [1, 2, 3, 4, 5]
    processed_numbers = process_list(numbers)
    print(f"Processed numbers: {processed_numbers}")

    # Test class usage
    processor = DataProcessor("TestProcessor")
    processor.add_data("hello")
    processor.add_data("world")
    processor.add_data(42)

    processed_data = processor.process_all()
    print(f"Processed data: {processed_data}")
    print(f"Total items processed: {processor.processed_count}")

    # Test division (uncomment to test exception handling)
    # result = divide_numbers(10, 0)

    # Test with command line arguments
    if len(sys.argv) > 1:
        print(f"Command line arguments: {sys.argv[1:]}")

        # If first argument is a number, calculate its factorial
        try:
            arg_num = int(sys.argv[1])
            arg_fact = calculate_factorial(arg_num)
            print(f"Factorial of {arg_num} is {arg_fact}")
        except ValueError:
            print(f"First argument '{sys.argv[1]}' is not a valid number")

    print("Test script completed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
