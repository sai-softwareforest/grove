# Reminder emails: no gateway yet

The README says members with overdue books get an email every Monday.
Only `reminderText` exists, which builds the text. Nothing sends it.

Options looked at: the office SMTP server (needs a service account) or a
hosted provider with an HTTP API. No decision yet.
