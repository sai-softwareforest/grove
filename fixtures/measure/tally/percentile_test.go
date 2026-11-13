package main

import "testing"

func TestPercentileNearestRank(t *testing.T) {
	values := []float64{15, 20, 35, 40, 50}
	for p, want := range map[float64]float64{30: 20, 40: 20, 50: 35, 100: 50} {
		if got, _ := Percentile(values, p); got != want {
			t.Errorf("p%v: got %v, want %v", p, got, want)
		}
	}
}

func TestPercentileNeedsFiveValues(t *testing.T) {
	if _, ok := Percentile([]float64{1, 2, 3, 4}, 50); ok {
		t.Fatal("four values gave a percentile")
	}
}
