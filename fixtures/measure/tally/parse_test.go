package main

import "testing"

const sample = `203.0.113.9 - - [10/Oct/2026:13:55:36 +0000] "GET /search?q=a HTTP/1.1" 200 2326 0.012`

func TestParseLineReadsPathStatusAndTime(t *testing.T) {
	request, err := ParseLine(sample)
	if err != nil {
		t.Fatal(err)
	}
	if request.Status != 200 || request.Minute != "10/Oct/2026:13:55" || request.Millis != 12 {
		t.Fatalf("got %+v", request)
	}
}

func TestParseLineSkipsCommentsAndBlankLines(t *testing.T) {
	for _, line := range []string{"", "   ", "# rotated"} {
		if _, err := ParseLine(line); err != errSkip {
			t.Fatalf("%q: got %v", line, err)
		}
	}
}

func TestParseLineDropsTheQueryString(t *testing.T) {
	request, _ := ParseLine(sample)
	if request.Path != "/search" {
		t.Fatalf("got %q", request.Path)
	}
}
