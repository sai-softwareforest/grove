package main

import (
	"math"
	"sort"
)

const minSamples = 5

// Percentile returns the nearest-rank percentile p (0 < p <= 100) of values.
// ok is false when there are fewer than minSamples values.
func Percentile(values []float64, p float64) (result float64, ok bool) {
	if len(values) < minSamples {
		return 0, false
	}
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	rank := int(math.Ceil(p / 100 * float64(len(sorted))))
	if rank < 1 {
		rank = 1
	}
	return sorted[rank-1], true
}
