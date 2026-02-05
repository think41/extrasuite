# InsertPersonRequest

Inserts a person mention.

**Type:** object

## Properties

- **location** ([Location](location.md)): Inserts the person mention at a specific index in the document. The person mention must be inserted inside the bounds of an existing Paragraph. For instance, it cannot be inserted at a table's start index (i.e. between the table and its preceding paragraph). People cannot be inserted inside an equation.
- **endOfSegmentLocation** ([EndOfSegmentLocation](endofsegmentlocation.md)): Inserts the person mention at the end of a header, footer, footnote or the document body.
- **personProperties** ([PersonProperties](personproperties.md)): The properties of the person mention to insert.
