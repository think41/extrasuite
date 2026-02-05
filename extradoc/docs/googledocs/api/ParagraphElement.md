# ParagraphElement

A ParagraphElement describes content within a Paragraph.

**Type:** object

## Properties

- **startIndex** (integer): The zero-based start index of this paragraph element, in UTF-16 code units.
- **endIndex** (integer): The zero-base end index of this paragraph element, exclusive, in UTF-16 code units.
- **textRun** ([TextRun](textrun.md)): A text run paragraph element.
- **autoText** ([AutoText](autotext.md)): An auto text paragraph element.
- **pageBreak** ([PageBreak](pagebreak.md)): A page break paragraph element.
- **columnBreak** ([ColumnBreak](columnbreak.md)): A column break paragraph element.
- **footnoteReference** ([FootnoteReference](footnotereference.md)): A footnote reference paragraph element.
- **horizontalRule** ([HorizontalRule](horizontalrule.md)): A horizontal rule paragraph element.
- **equation** ([Equation](equation.md)): An equation paragraph element.
- **inlineObjectElement** ([InlineObjectElement](inlineobjectelement.md)): An inline object paragraph element.
- **person** ([Person](person.md)): A paragraph element that links to a person or email address.
- **richLink** ([RichLink](richlink.md)): A paragraph element that links to a Google resource (such as a file in Google Drive, a YouTube video, or a Calendar event.)
- **dateElement** ([DateElement](dateelement.md)): A paragraph element that represents a date.
