# Parcel — architecture map

Written by reading the source in one afternoon; nothing was run.

Evidence labels used below:

- `documented` — stated in the README.
- `observed-in-code` — read in the source files.
- `untested` — no test was found for it.

## Pricing

- `rates.quote` adds the zone's base price and a price per kilo, then the fuel surcharge (`documented`, `observed-in-code`).
- Prices are `Decimal` values, rounded with `ROUND_CEILING` (`observed-in-code`).
- An unknown postcode area falls back to zone D without a warning (`observed-in-code`, `untested`).

## Size and weight

- `validate.check_size` is never called by `quote` or by the command line; a caller has to remember it (`observed-in-code`, `untested`).
- The 30 kg limit has a test, the 150 cm limit has none.

## Tracking

- A code is `PX`, nine digits and a check digit (`documented`).
- `is_valid` accepts no prefix other than `PX` (`observed-in-code`).

## Labels

`labels.format_label` drops blank lines and keeps at most two extra lines. It is untested.

## Open questions

- The README promises an email to the customer; no code sends one (`documented`).
- `audit.py` keeps its entries in a list in memory, so they are lost when the process ends (`observed-in-code`, `untested`).
