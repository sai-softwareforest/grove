import type { Book } from "./catalogue";

export const LOAN_DAYS = 21;
export const MAX_LOANS = 3;
export const FINE_PER_DAY = 0.2;
const DAY_MS = 24 * 60 * 60 * 1000;

export interface Loan {
  isbn: string;
  member: string;
  due: Date;
}

export function dueDate(start: Date): Date {
  return new Date(start.getTime() + LOAN_DAYS * DAY_MS);
}

export function daysLate(loan: Loan, today: Date): number {
  return Math.max(0, Math.floor((today.getTime() - loan.due.getTime()) / DAY_MS));
}

export function lend(loans: Loan[], member: string, book: Book, today: Date): Loan {
  const held = loans.filter((loan) => loan.member === member);
  if (held.length >= MAX_LOANS) throw new Error("three books already");
  if (held.some((loan) => daysLate(loan, today) > 0)) throw new Error("an overdue book comes first");
  const loan = { isbn: book.isbn, member, due: dueDate(today) };
  loans.push(loan);
  return loan;
}

export function giveBack(loans: Loan[], member: string, isbn: string): Loan {
  const index = loans.findIndex((loan) => loan.member === member && loan.isbn === isbn);
  if (index < 0) throw new Error("not on loan");
  return loans.splice(index, 1)[0];
}

export const overdue = (loans: Loan[], today: Date): Loan[] =>
  loans.filter((loan) => daysLate(loan, today) > 0).sort((a, b) => a.due.getTime() - b.due.getTime());

export function fine(loan: Loan, book: Book, today: Date): number {
  return Math.min(book.price, daysLate(loan, today) * FINE_PER_DAY);
}
