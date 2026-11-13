# Shelf

Shelf keeps track of the books in a small office library: what is on the
shelf, who has borrowed what, and what is overdue. Everything lives in
memory and in one JSON file.

## Getting started

```sh
npm install
npm test
```

Node 20 or newer is required.

## Features

### Catalogue

Books are identified by their ISBN-13. Adding a book twice increases the
number of copies instead of creating a second entry. Titles can be searched
without regard to case, and a search for an empty string returns nothing.
A book cannot be removed while a copy is on loan. The catalogue can be
exported as CSV for the yearly stock check.

### Loans

A member may hold at most three books at a time. Loans run for 21 days.
Overdue loans are listed oldest first. The fine is 20 pence per day and
never exceeds the price of the book. See [the loan rules](docs/loans.md)
for the details.

### ISBN

ISBN-10 numbers are converted to ISBN-13 on input. Hyphens and spaces are
ignored. An ISBN with a wrong check digit is rejected.

### Reminders

Each Monday, Shelf emails a reminder to every member with an overdue book.

## Storage

`save` writes the whole library to one JSON file and `load` reads it back.
Writes are atomic: the file is replaced, never edited in place.

## Known issues

- Two people editing the same file at once will overwrite each other.
- Renewals are not supported yet.
