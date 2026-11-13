import type { Loan } from "./loans";

// How often each book was borrowed, the most borrowed first.
export function mostBorrowed(history: Loan[], top = 5): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const loan of history) {
    counts.set(loan.isbn, (counts.get(loan.isbn) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, top);
}
