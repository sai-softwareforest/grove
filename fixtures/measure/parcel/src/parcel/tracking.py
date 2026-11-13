"""Tracking codes: a prefix, nine digits and a check digit."""

PREFIX = "PX"


def check_digit(digits: str) -> int:
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(digits))
    return (10 - total % 10) % 10


def new_code(sequence: int) -> str:
    digits = f"{sequence:09d}"
    return f"{PREFIX}{digits}{check_digit(digits)}"


def is_valid(code: str) -> bool:
    body = code[len(PREFIX):]
    if not code.startswith(PREFIX) or len(body) != 10 or not body.isdigit():
        return False
    return check_digit(body[:9]) == int(body[9])
