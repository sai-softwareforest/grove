"""Price a shipment from its weight and destination zone."""

from decimal import ROUND_CEILING, Decimal

ZONE_BASE = {"A": Decimal("3.20"), "B": Decimal("4.10"), "C": Decimal("5.75"), "D": Decimal("7.40")}
PER_KG = Decimal("0.85")
FUEL_SURCHARGE = Decimal("0.04")
MAX_KG = 30
_ZONE_BY_LETTER = {"N": "A", "E": "A", "S": "B", "W": "B", "M": "C", "L": "C"}


def zone_for(postcode: str) -> str:
    """The zone of a postcode, read from its first letter; any other area is zone D."""
    return _ZONE_BY_LETTER.get(postcode.strip().upper()[:1], "D")


def quote(weight_kg: float, zone: str) -> Decimal:
    """The price in pounds for one box."""
    if weight_kg <= 0:
        raise ValueError("the weight must be more than zero")
    if weight_kg > MAX_KG:
        raise ValueError(f"over {MAX_KG} kg")
    price = (ZONE_BASE[zone] + PER_KG * Decimal(str(weight_kg))) * (1 + FUEL_SURCHARGE)
    return price.quantize(Decimal("0.01"), rounding=ROUND_CEILING)
