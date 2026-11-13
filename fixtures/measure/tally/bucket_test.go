package main

import "testing"

func TestTopSortsByCountThenKey(t *testing.T) {
	tally := NewTally(false)
	for _, path := range []string{"/b", "/a", "/c", "/c"} {
		tally.Add(Request{Path: path})
	}
	rows := tally.Top(0)
	if len(rows) != 3 || rows[0].Key != "/c" || rows[1].Key != "/a" || rows[2].Key != "/b" {
		t.Fatalf("got %v, %v, %v", rows[0].Key, rows[1].Key, rows[2].Key)
	}
}
