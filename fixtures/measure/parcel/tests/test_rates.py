from decimal import Decimal

import pytest

from parcel.rates import quote, zone_for


def test_quote_for_zone_b():
    assert quote(2.5, "B") == Decimal("6.48")


def test_zero_weight_is_an_error():
    with pytest.raises(ValueError):
        quote(0, "A")


def test_too_heavy_is_an_error():
    with pytest.raises(ValueError):
        quote(30.5, "A")


def test_postcode_is_cleaned_before_lookup():
    assert zone_for("  sw1a 1aa ") == "B"
