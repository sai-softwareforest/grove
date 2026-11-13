# Fuel surcharge

The fuel surcharge is 4% of the price before rounding. It is one constant,
`FUEL_SURCHARGE` in `rates.py`. The carrier reviews it every quarter, so
expect to change it four times a year.

Changing it also changes the expected price in `test_quote_for_zone_b`.
