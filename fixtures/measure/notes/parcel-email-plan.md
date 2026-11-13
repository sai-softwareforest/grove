# Plan: tell the customer when a label is printed

The README promises an email to the customer when a label is printed.
Nothing is built yet.

Plan:

1. Put a message on a queue when `format_label` is called from the print
   station.
2. A worker sends the message through the company SMTP relay.
3. Three retries, then the message goes to a dead-letter list.

Open: who owns the wording of the message.
