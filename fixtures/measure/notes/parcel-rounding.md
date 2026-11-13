# Why prices round up

Decision, agreed with the warehouse manager: a price is always rounded up
to the next whole cent, never to the nearest one. The customer may pay a
fraction of a cent too much; the warehouse never charges too little.

In code this is `Decimal.quantize` with `ROUND_CEILING` in `rates.py`.
Floats are not used anywhere in the price: 6.474 has to become 6.48 and a
float would not promise that.
