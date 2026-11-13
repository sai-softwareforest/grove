package main

import "sort"

// Counts holds what was seen for one key.
type Counts struct {
	Key    string
	Total  int
	Millis []float64
}

// Tally groups requests by path, or by minute and path.
type Tally struct {
	byMinute bool
	groups   map[string]*Counts
	Bad      int
}

func NewTally(byMinute bool) *Tally {
	return &Tally{byMinute: byMinute, groups: map[string]*Counts{}}
}

func (t *Tally) Add(r Request) {
	key := r.Path
	if t.byMinute {
		key = r.Minute + " " + r.Path
	}
	counts := t.groups[key]
	if counts == nil {
		counts = &Counts{Key: key}
		t.groups[key] = counts
	}
	counts.Total++
	counts.observe(r.Millis)
}

// Top returns the n busiest keys, largest first, ties by key. All of them when n is 0.
func (t *Tally) Top(n int) []*Counts {
	rows := make([]*Counts, 0, len(t.groups))
	for _, counts := range t.groups {
		rows = append(rows, counts)
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].Total != rows[j].Total {
			return rows[i].Total > rows[j].Total
		}
		return rows[i].Key < rows[j].Key
	})
	if n > 0 && n < len(rows) {
		rows = rows[:n]
	}
	return rows
}
