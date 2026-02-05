# Work with Tabs

The Google Docs API enables developers to access content from any tab within a document. Tabs function as an organizational layer, allowing users to create multiple tabs within a single document—similar to how tabs work in Google Sheets. Each tab has its own unique title and ID, and can contain child tabs nested beneath it.

## What Are Tabs?

Tabs represent a structural feature in Google Docs that provides document organization. Users can create one or more tabs, each with an ID appended in the URL. Child tabs can be nested beneath parent tabs to create hierarchical structures.

## Structural Changes to Document Resources

Previously, documents lacked tab functionality, and all content was stored directly in the `Document` resource via these fields:

- `document.body`
- `document.headers`
- `document.footers`
- `document.footnotes`
- `document.documentStyle`
- `document.lists`
- `document.namedRanges`
- `document.inlineObjects`
- `document.positionedObjects`

With tabs introduced, content structure shifted. Text-based content is now accessed through `document.tabs`, which contains a list of `Tab` objects. Each `Tab` object holds all previously mentioned fields within a `DocumentTab` property.

### Accessing Tab Properties

Use `tab.tabProperties` to access tab metadata including ID, title, and positioning information.

### Accessing Text Content

Content within a tab is exposed via `tab.documentTab`. Instead of `document.body`, use `document.tabs[indexOfTab].documentTab.body`.

### Tab Hierarchy

Child tabs are represented in `tab.childTabs`. Traversing all tabs requires navigating the tree structure. For example, accessing the body of a nested tab might look like: `document.tabs[2].childTabs[0].childTabs[1].documentTab.body`.

## Method Changes

### documents.get

The `includeTabsContent` parameter controls whether all tabs are returned:

- When `true`: Returns all tab contents in `document.tabs`; legacy fields remain empty
- When omitted: Returns content from the first tab only; `document.tabs` remains empty

### documents.create

Returns a `Document` resource representing the new empty document with contents populated in both legacy fields and `document.tabs`.

### documents.batchUpdate

Each `Request` can specify target tabs. If unspecified, most requests default to the first tab. Exceptions include `ReplaceAllTextRequest`, `DeleteNamedRangeRequest`, and `ReplaceNamedRangeContentRequest`, which apply to all tabs by default.

See @best-practices.md for tab handling best practices.

## Internal Link Updates

With tabs, internal links require updated field usage:

- Use `link.bookmark` and `link.heading` instead of legacy `link.bookmarkId` and `link.headingId`
- New fields expose `BookmarkLink` and `HeadingLink` objects containing both the element ID and its tab ID
- `link.tabId` provides direct tab references

## Common Usage Patterns

### Reading All Tab Content

Set `includeTabsContent` to `true`, traverse the tab tree, and call getter methods on `Tab` and `DocumentTab` objects.

### Reading First Tab Content

Similar to reading all tabs, but process only the first element after flattening the tab hierarchy.

### Updating Specific Tabs

Specify the tab ID in the `Location` object within your request to target a particular tab for updates.
