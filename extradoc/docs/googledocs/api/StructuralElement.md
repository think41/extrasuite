# StructuralElement

A StructuralElement describes content that provides structure to the document.

**Type:** object

## Properties

- **startIndex** (integer): The zero-based start index of this structural element, in UTF-16 code units.
- **endIndex** (integer): The zero-based end index of this structural element, exclusive, in UTF-16 code units.
- **paragraph** ([Paragraph](paragraph.md)): A paragraph type of structural element.
- **sectionBreak** ([SectionBreak](sectionbreak.md)): A section break type of structural element.
- **table** ([Table](table.md)): A table type of structural element.
- **tableOfContents** ([TableOfContents](tableofcontents.md)): A table of contents type of structural element.
