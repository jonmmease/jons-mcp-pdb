#!/usr/bin/env python3
"""Test script for debugging"""


def factorial(n):
    """Calculate factorial of n"""
    if n <= 1:
        return 1
    result = n * factorial(n - 1)
    return result


def main():
    print("Starting factorial calculation")
    numbers = [5, 3, 7]

    for num in numbers:
        fact = factorial(num)
        print(f"factorial({num}) = {fact}")

    print("Done!")


if __name__ == "__main__":
    main()
