# ReplaceNamedRangeContentRequest

Replaces the contents of the specified NamedRange or NamedRanges with the given replacement content. Note that an individual NamedRange may consist of multiple discontinuous ranges. In this case, only the content in the first range will be replaced. The other ranges and their content will be deleted. In cases where replacing or deleting any ranges would result in an invalid document structure, a 400 bad request error is returned.

**Type:** object

## Properties

- **text** (string): Replaces the content of the specified named range(s) with the given text.
- **namedRangeId** (string): The ID of the named range whose content will be replaced. If there is no named range with the given ID a 400 bad request error is returned.
- **namedRangeName** (string): The name of the NamedRanges whose content will be replaced. If there are multiple named ranges with the given name, then the content of each one will be replaced. If there are no named ranges with the given name, then the request will be a no-op.
- **tabsCriteria** ([TabsCriteria](tabscriteria.md)): Optional. The criteria used to specify in which tabs the replacement occurs. When omitted, the replacement applies to all tabs. In a document containing a single tab: - If provided, must match the singular tab's ID. - If omitted, the replacement applies to the singular tab. In a document containing multiple tabs: - If provided, the replacement applies to the specified tabs. - If omitted, the replacement applies to all tabs.
