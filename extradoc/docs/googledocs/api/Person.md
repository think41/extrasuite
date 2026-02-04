# Person

A person or email address mentioned in a document. These mentions behave as a single, immutable element containing the person's name or email address.

**Type:** object

## Properties

- **personId** (string): Output only. The unique ID of this link.
- **suggestedInsertionIds** (array of string): IDs for suggestions that insert this person link into the document. A Person might have multiple insertion IDs if it's a nested suggested change (a suggestion within a suggestion made by a different user, for example). If empty, then this person link isn't a suggested insertion.
- **suggestedDeletionIds** (array of string): IDs for suggestions that remove this person link from the document. A Person might have multiple deletion IDs if, for example, multiple users suggest deleting it. If empty, then this person link isn't suggested for deletion.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this Person.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this Person, keyed by suggestion ID.
- **personProperties** ([PersonProperties](personproperties.md)): Output only. The properties of this Person. This field is always present.
