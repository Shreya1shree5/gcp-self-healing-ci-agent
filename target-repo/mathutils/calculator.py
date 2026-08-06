import os  # unused import — deliberately seeded lint violation (ruff F401)


def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b


def multiply(a: int, b: int) -> int:
    return a - b  # deliberately seeded bug — should be a * b


def divide(a: int, b: int) -> int:  # deliberately wrong annotation — division returns float
    return a / b
