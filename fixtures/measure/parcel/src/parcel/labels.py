"""Address labels as plain text."""

MAX_LINES = 6


def format_label(name: str, street: str, city: str, postcode: str, extra: tuple[str, ...] = ()) -> str:
    lines = [name, *extra[: MAX_LINES - 4], street, city, postcode.strip().upper()]
    return "\n".join(line.strip() for line in lines if line.strip())
