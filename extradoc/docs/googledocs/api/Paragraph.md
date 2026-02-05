# Paragraph

A StructuralElement representing a paragraph. A paragraph is a range of content that's terminated with a newline character.

**Type:** object

## Properties

- **elements** (array of [ParagraphElement](paragraphelement.md)): The content of the paragraph, broken down into its component parts.
- **paragraphStyle** ([ParagraphStyle](paragraphstyle.md)): The style of this paragraph.
- **suggestedParagraphStyleChanges** (object): The suggested paragraph style changes to this paragraph, keyed by suggestion ID.
- **bullet** ([Bullet](bullet.md)): The bullet for this paragraph. If not present, the paragraph does not belong to a list.
- **suggestedBulletChanges** (object): The suggested changes to this paragraph's bullet.
- **positionedObjectIds** (array of string): The IDs of the positioned objects tethered to this paragraph.
- **suggestedPositionedObjectIds** (object): The IDs of the positioned objects suggested to be attached to this paragraph, keyed by suggestion ID.
