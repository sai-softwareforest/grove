"""A running record of the quotes given, for the monthly reconciliation."""

from decimal import Decimal

_entries: list[tuple[str, Decimal]] = []


def record(zone: str, price: Decimal) -> None:
    _entries.append((zone, price))


def total_by_zone() -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for zone, price in _entries:
        totals[zone] = totals.get(zone, Decimal("0")) + price
    return totals
