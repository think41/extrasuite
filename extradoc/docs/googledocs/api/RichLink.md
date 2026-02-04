# RichLink

A link to a Google resource (such as a file in Drive, a YouTube video, or a Calendar event).

**Type:** object

## Properties

- **richLinkId** (string): Output only. The ID of this link.
- **suggestedInsertionIds** (array of string): IDs for suggestions that insert this link into the document. A RichLink might have multiple insertion IDs if it's a nested suggested change (a suggestion within a suggestion made by a different user, for example). If empty, then this person link isn't a suggested insertion.
- **suggestedDeletionIds** (array of string): IDs for suggestions that remove this link from the document. A RichLink might have multiple deletion IDs if, for example, multiple users suggest deleting it. If empty, then this person link isn't suggested for deletion.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this RichLink.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this RichLink, keyed by suggestion ID.
- **richLinkProperties** ([RichLinkProperties](richlinkproperties.md)): Output only. The properties of this RichLink. This field is always present.
