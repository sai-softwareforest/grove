import { expect, test } from "vitest";
import { dueDate, fine, giveBack, lend, type Loan } from "../src/loans";

const book = { isbn: "9780306406157", title: "Advanced Engineering Mathematics", copies: 4, price: 45 };
const day = (text: string) => new Date(text + "T00:00:00Z");

test("a loan is due three weeks later", () => {
  expect(dueDate(day("2026-03-01"))).toEqual(day("2026-03-22"));
});

test("a fourth book is refused", () => {
  const loans: Loan[] = [];
  for (let i = 0; i < 3; i++) lend(loans, "ana", book, day("2026-03-01"));
  expect(() => lend(loans, "ana", book, day("2026-03-02"))).toThrow("three books");
});

test("the fine grows by the day and stops at the price of the book", () => {
  const loan = { isbn: book.isbn, member: "ana", due: day("2026-03-22") };
  expect(fine(loan, book, day("2026-03-27"))).toBeCloseTo(1.0);
  expect(fine(loan, book, day("2027-06-01"))).toBe(45);
});

test("giving back a book that was never lent throws", () => {
  expect(() => giveBack([], "ana", book.isbn)).toThrow("not on loan");
});
