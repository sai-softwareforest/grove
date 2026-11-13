package main

import (
	"errors"
	"strconv"
	"strings"
)

// Request is one parsed log line.
type Request struct {
	Path   string
	Status int
	Minute string
	Millis float64
}

var errSkip = errors.New("skip")
var errFormat = errors.New("not a log line")

// ParseLine reads one line in the common log format with a trailing
// response time in seconds.
func ParseLine(line string) (Request, error) {
	line = strings.TrimSpace(line)
	if line == "" || strings.HasPrefix(line, "#") {
		return Request{}, errSkip
	}
	open, shut := strings.IndexByte(line, '['), strings.IndexByte(line, ']')
	first, last := strings.IndexByte(line, '"'), strings.LastIndexByte(line, '"')
	if open < 0 || shut < open || first < shut || last <= first {
		return Request{}, errFormat
	}
	request := strings.Fields(line[first+1 : last])
	tail := strings.Fields(line[last+1:])
	if len(request) < 2 || len(tail) < 3 {
		return Request{}, errFormat
	}
	status, err := strconv.Atoi(tail[0])
	if err != nil {
		return Request{}, errFormat
	}
	seconds, err := strconv.ParseFloat(tail[len(tail)-1], 64)
	if err != nil {
		return Request{}, errFormat
	}
	minute := line[open+1 : shut]
	if len(minute) > 17 {
		minute = minute[:17]
	}
	return Request{Path: stripQuery(request[1]), Status: status, Minute: minute, Millis: seconds * 1000}, nil
}

func stripQuery(path string) string {
	if i := strings.IndexByte(path, '?'); i >= 0 {
		return path[:i]
	}
	return path
}
