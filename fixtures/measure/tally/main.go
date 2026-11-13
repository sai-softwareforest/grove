package main

import (
	"bufio"
	"flag"
	"fmt"
	"io"
	"os"
)

func main() {
	top := flag.Int("top", 0, "print only the N busiest paths")
	asJSON := flag.Bool("json", false, "print JSON instead of a table")
	byMinute := flag.Bool("by-minute", false, "group by minute as well as by path")
	flag.Parse()

	var input io.Reader = os.Stdin
	if flag.NArg() > 0 {
		file, err := os.Open(flag.Arg(0))
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		defer file.Close()
		input = file
	}

	tally := NewTally(*byMinute)
	scanner := bufio.NewScanner(input)
	for scanner.Scan() {
		request, err := ParseLine(scanner.Text())
		switch err {
		case nil:
			tally.Add(request)
		case errSkip:
		default:
			tally.Bad++
		}
	}
	if err := scanner.Err(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	if *asJSON {
		if err := RenderJSON(os.Stdout, tally.Top(*top)); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	} else {
		RenderText(os.Stdout, tally.Top(*top))
	}
	if tally.Bad > 0 {
		fmt.Fprintf(os.Stderr, "%d lines could not be parsed\n", tally.Bad)
	}
}
