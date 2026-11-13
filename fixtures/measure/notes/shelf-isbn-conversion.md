# Converting ISBN-10 to ISBN-13

Take the first nine digits of the ISBN-10, put 978 in front and compute a
new check digit with the weights 1 and 3. The old check digit, which may
be an X, is thrown away.

Example: 0306406152 becomes 9780306406157.
