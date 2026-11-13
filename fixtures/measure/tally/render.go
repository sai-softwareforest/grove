package main

import (
	"encoding/json"
	"fmt"
	"io"
	"text/tabwriter"
)

func cell(values []float64, p float64) string {
	if value, ok := Percentile(values, p); ok {
		return fmt.Sprintf("%.0f", value)
	}
	return "-"
}

// RenderText writes one row per key: count, then the 50th, 90th and 99th percentile in milliseconds.
func RenderText(w io.Writer, rows []*Counts) {
	table := tabwriter.NewWriter(w, 0, 8, 2, ' ', 0)
	fmt.Fprintln(table, "COUNT\tP50\tP90\tP99\tPATH")
	for _, row := range rows {
		fmt.Fprintf(table, "%d\t%s\t%s\t%s\t%s\n", row.Total, cell(row.Millis, 50), cell(row.Millis, 90), cell(row.Millis, 99), row.Key)
	}
	table.Flush()
}

// RenderJSON writes one JSON object per key, one per line.
func RenderJSON(w io.Writer, rows []*Counts) error {
	encoder := json.NewEncoder(w)
	for _, row := range rows {
		p50, _ := Percentile(row.Millis, 50)
		p99, _ := Percentile(row.Millis, 99)
		if err := encoder.Encode(map[string]any{"path": row.Key, "count": row.Total, "p50": p50, "p99": p99}); err != nil {
			return err
		}
	}
	return nil
}
