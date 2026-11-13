import type { Loan } from "./loans";

export function reminderText(member: string, loans: Loan[]): string {
  const lines = loans.map((loan) => `- ${loan.isbn}, due ${loan.due.toISOString().slice(0, 10)}`);
  return [`Dear ${member},`, "these books are overdue:", ...lines].join("\n");
}
