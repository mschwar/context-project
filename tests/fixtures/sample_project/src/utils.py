"""Utility functions for string formatting and math."""


def format_name(name: str) -> str:
    """Capitalize and strip whitespace from a name."""
    return name.strip().title()


def calculate_total(numbers: list[int]) -> int:
    """Sum a list of integers."""
    return sum(numbers)
