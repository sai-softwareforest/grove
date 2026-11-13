# Capping memory with reservoir sampling

A busy path can have millions of requests, and keeping every response
time made tally use several gigabytes on the production logs. `sample.go`
now keeps at most 10 000 response times per key. After that a new value
replaces a kept one at random, so the kept values stay a fair sample.

Side effect: the generator is seeded from the clock, so two runs over the
same log can print slightly different percentiles for the busiest paths.
