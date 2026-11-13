# Percentiles: nearest rank

tally uses the nearest-rank method: sort the response times and take the
value at position ceil(p / 100 * n). No interpolation, so every percentile
printed is a response time that really happened.

With fewer than five requests no percentile is given: the 99th percentile
of three values means nothing.
