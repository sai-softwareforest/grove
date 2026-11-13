# Atomic writes for shelf.json

`save` writes the library to a temporary file next to `shelf.json` and
then renames it over the old file. A reader sees the old file or the new
one, never half of one.

Not done: fsync before the rename, so a power cut can still lose the last
change. Two editors at once still overwrite each other; there is no lock.
