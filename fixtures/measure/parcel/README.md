# Parcel

Parcel is a small library for pricing and labelling domestic shipments.
It grew out of a spreadsheet that a warehouse used for a few hundred boxes a day.

## Installation

Parcel needs Python 3.11 or newer and has no other dependency.

```sh
pip install parcel-rates
```

## What it does

- Prices a shipment from its weight and its destination zone.
- Every price is rounded up to the next whole cent.
- A fuel surcharge of 4% is added to every price.
- A weight of zero or less raises `ValueError`.
- Refuses a box whose longest side is over 150 cm.
- Postcodes are trimmed and upper-cased before the zone lookup.
- Generates tracking codes that end in a check digit, so a single mistyped character is caught.
- Formats an address label of at most six lines.
- Sends the customer an email when a label is printed.
- Prices can be quoted in euros or in pounds.

## Command line

Run `parcel quote 2.5 --zone B` to print a price.
The command exits with status 2 when an argument is missing or malformed.

## Limits

- Only the domestic zones A to D are known.
- International shipments are not supported.
- Anything heavier than 30 kg is refused, not priced.

## Thanks

Thanks to the night shift for the sample data.

## Licence

MIT.
