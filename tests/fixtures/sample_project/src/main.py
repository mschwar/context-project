"""Main entry point for the sample application."""

from utils import format_name, calculate_total


def main():
    name = format_name("world")
    total = calculate_total([1, 2, 3, 4, 5])
    print(f"Hello, {name}! Total is {total}.")


if __name__ == "__main__":
    main()
