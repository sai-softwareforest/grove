# check_size is never called

Finding from reading the source: `validate.check_size` refuses a box
whose longest side is over 150 cm, but neither `quote` nor the command
line calls it. A box of any size gets a price today.

Work to do: call it from `cli.main` before `quote`, and add a test.
