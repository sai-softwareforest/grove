# Shelf: map

Every row and every item carries the evidence for its claim. `documented`
means the README or `docs/loans.md` says so, `observed-in-code` means the
source was read, `untested` means no test covers it.

## Modules

| Module | What it does | Evidence |
|---|---|---|
| `src/isbn.ts` | Cleans the input, converts ISBN-10, verifies the check digit | documented, observed-in-code |
| `src/catalogue.ts` | Holds books by ISBN-13 and counts copies | documented, observed-in-code |
| `src/loans.ts` | Lending, giving back, the overdue list and fines | documented, observed-in-code |
| `src/storage.ts` | Writes a temporary file and renames it over the old one | observed-in-code, untested |
| `src/reminders.ts` | Builds the text of a reminder; sends nothing | observed-in-code, untested |
| `src/stats.ts` | Counts how often each book was borrowed | observed-in-code, untested |
| `src/members.ts` | Turns an email address or a badge number into a member id | observed-in-code, untested |

## Behaviour without a test

Untested:

- `Catalogue.remove` trusts the caller to pass the number of copies on loan.
- `overdue` sorts by due date; two loans due on the same day keep the order they were made in.
- A member who holds three books and is also overdue gets the "three books" error, not the overdue one.

## Notes

The check digit is the best covered part of the project: nothing in
`src/isbn.ts` is untested. The weekly email of the README is documented
but does not exist.
