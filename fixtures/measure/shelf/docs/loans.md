# Loan rules

These are the rules the code in `src/loans.ts` enforces.

1. A loan starts on the day the book is handed over and runs for 21 days.
2. A member with an overdue book cannot borrow another one.
3. Returning a book that is not on loan is an error.
4. Fines are counted in whole days; the day the book was due is free.

## Reminders

`src/reminders.ts` only builds the text of a reminder. Nothing is sent
yet: the mail gateway has not been chosen.
