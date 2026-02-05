# InsertDateRequest

Inserts a date at the specified location.

**Type:** object

## Properties

- **location** ([Location](location.md)): Inserts the date at a specific index in the document. The date must be inserted inside the bounds of an existing Paragraph. For instance, it cannot be inserted at a table's start index (i.e. between an existing table and its preceding paragraph).
- **endOfSegmentLocation** ([EndOfSegmentLocation](endofsegmentlocation.md)): Inserts the date at the end of the given header, footer or document body.
- **dateElementProperties** ([DateElementProperties](dateelementproperties.md)): The properties of the date to insert.
