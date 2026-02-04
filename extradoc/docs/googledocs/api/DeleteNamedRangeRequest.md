# DeleteNamedRangeRequest

Deletes a NamedRange.

**Type:** object

## Properties

- **namedRangeId** (string): The ID of the named range to delete.
- **name** (string): The name of the range(s) to delete. All named ranges with the given name will be deleted.
- **tabsCriteria** ([TabsCriteria](tabscriteria.md)): Optional. The criteria used to specify which tab(s) the range deletion should occur in. When omitted, the range deletion is applied to all tabs. In a document containing a single tab: - If provided, must match the singular tab's ID. - If omitted, the range deletion applies to the singular tab. In a document containing multiple tabs: - If provided, the range deletion applies to the specified tabs. - If not provided, the range deletion applies to all tabs.
