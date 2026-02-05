# DateElement

A date instance mentioned in a document.

**Type:** object

## Properties

- **dateId** (string): Output only. The unique ID of this date.
- **suggestedInsertionIds** (array of string): IDs for suggestions that insert this date into the document. A DateElement might have multiple insertion IDs if it's a nested suggested change (a suggestion within a suggestion made by a different user, for example). If empty, then this date isn't a suggested insertion.
- **suggestedDeletionIds** (array of string): IDs for suggestions that remove this date from the document. A DateElement might have multiple deletion IDs if, for example, multiple users suggest deleting it. If empty, then this date isn't suggested for deletion.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this DateElement.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this DateElement, keyed by suggestion ID.
- **dateElementProperties** ([DateElementProperties](dateelementproperties.md)): The properties of this DateElement.
- **suggestedDateElementPropertiesChanges** (object): The suggested changes to the date element properties, keyed by suggestion ID.
