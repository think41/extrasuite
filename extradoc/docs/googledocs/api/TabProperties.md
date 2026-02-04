# TabProperties

Properties of a tab.

**Type:** object

## Properties

- **tabId** (string): The immutable ID of the tab.
- **title** (string): The user-visible name of the tab.
- **parentTabId** (string): Optional. The ID of the parent tab. Empty when the current tab is a root-level tab, which means it doesn't have any parents.
- **index** (integer): The zero-based index of the tab within the parent.
- **nestingLevel** (integer): Output only. The depth of the tab within the document. Root-level tabs start at 0.
- **iconEmoji** (string): Optional. The emoji icon displayed with the tab. A valid emoji icon is represented by a non-empty Unicode string. Any set of characters that don't represent a single emoji is invalid. If an emoji is invalid, a 400 bad request error is returned. If this value is unset or empty, the tab will display the default tab icon.
