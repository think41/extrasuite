# CreateNamedRangeRequest

Creates a NamedRange referencing the given range.

**Type:** object

## Properties

- **name** (string): The name of the NamedRange. Names do not need to be unique. Names must be at least 1 character and no more than 256 characters, measured in UTF-16 code units.
- **range** ([Range](range.md)): The range to apply the name to.
