# SubstringMatchCriteria

A criteria that matches a specific string of text in the document.

**Type:** object

## Properties

- **text** (string): The text to search for in the document.
- **matchCase** (boolean): Indicates whether the search should respect case: - `True`: the search is case sensitive. - `False`: the search is case insensitive.
- **searchByRegex** (boolean): Optional. True if the find value should be treated as a regular expression. Any backslashes in the pattern should be escaped. - `True`: the search text is treated as a regular expressions. - `False`: the search text is treated as a substring for matching.
