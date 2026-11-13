package main

import (
	"math/rand"
	"time"
)

const maxSamples = 10000

var rng = rand.New(rand.NewSource(time.Now().UnixNano()))

// observe keeps at most maxSamples response times for a key. After that
// each new one replaces an earlier one with falling probability, so the
// kept values stay a fair sample of all of them.
func (c *Counts) observe(millis float64) {
	if len(c.Millis) < maxSamples {
		c.Millis = append(c.Millis, millis)
		return
	}
	if slot := rng.Intn(c.Total); slot < maxSamples {
		c.Millis[slot] = millis
	}
}
