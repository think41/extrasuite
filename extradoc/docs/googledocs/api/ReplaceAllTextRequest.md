# ReplaceAllTextRequest

Replaces all instances of text matching a criteria with replace text.

**Type:** object

## Properties

- **replaceText** (string): The text that will replace the matched text.
- **containsText** ([SubstringMatchCriteria](substringmatchcriteria.md)): Finds text in the document matching this substring.
- **tabsCriteria** ([TabsCriteria](tabscriteria.md)): Optional. The criteria used to specify in which tabs the replacement occurs. When omitted, the replacement applies to all tabs. In a document containing a single tab: - If provided, must match the singular tab's ID. - If omitted, the replacement applies to the singular tab. In a document containing multiple tabs: - If provided, the replacement applies to the specified tabs. - If omitted, the replacement applies to all tabs.
