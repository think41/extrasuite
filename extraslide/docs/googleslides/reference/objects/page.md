# Page

A page in a presentation (slide, master, layout, or notes page).

## Schema

```json
{
  "objectId": "string",
  "pageType": "SLIDE | MASTER | LAYOUT | NOTES | NOTES_MASTER",
  "pageElements": [PageElement],
  "pageProperties": PageProperties,
  "slideProperties": SlideProperties,
  "layoutProperties": LayoutProperties,
  "masterProperties": MasterProperties,
  "notesProperties": NotesProperties,
  "revisionId": "string"
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `objectId` | string | Unique identifier for the page |
| `pageType` | enum | Type of page |
| `pageElements` | [PageElement](./page-element.md)[] | Visual elements on the page |
| `pageProperties` | PageProperties | Page-level properties |
| `slideProperties` | SlideProperties | Slide-specific properties (SLIDE only) |
| `layoutProperties` | LayoutProperties | Layout-specific properties (LAYOUT only) |
| `masterProperties` | MasterProperties | Master-specific properties (MASTER only) |
| `notesProperties` | NotesProperties | Notes-specific properties (NOTES only) |
| `revisionId` | string | Revision ID (output only) |

## Page Types

| Type | Description |
|------|-------------|
| `SLIDE` | A presentation slide |
| `MASTER` | A slide master defining default styles |
| `LAYOUT` | A layout template |
| `NOTES` | Speaker notes page |
| `NOTES_MASTER` | Notes master (read-only) |

## SlideProperties

```json
{
  "layoutObjectId": "string",
  "masterObjectId": "string",
  "notesPage": Page,
  "isSkipped": boolean
}
```

| Property | Type | Description |
|----------|------|-------------|
| `layoutObjectId` | string | ID of the layout this slide uses |
| `masterObjectId` | string | ID of the master this slide uses |
| `notesPage` | Page | The notes page for this slide |
| `isSkipped` | boolean | Whether slide is skipped in presentation mode |

## LayoutProperties

```json
{
  "masterObjectId": "string",
  "name": "string",
  "displayName": "string"
}
```

| Property | Type | Description |
|----------|------|-------------|
| `masterObjectId` | string | ID of the master this layout belongs to |
| `name` | string | Internal name of the layout |
| `displayName` | string | Human-readable layout name |

## MasterProperties

```json
{
  "displayName": "string"
}
```

## NotesProperties

```json
{
  "speakerNotesObjectId": "string"
}
```

## PageProperties

```json
{
  "pageBackgroundFill": PageBackgroundFill,
  "colorScheme": ColorScheme
}
```

## Example: Slide

```json
{
  "objectId": "g1234567890",
  "pageType": "SLIDE",
  "pageElements": [
    {
      "objectId": "g1234567890_0",
      "size": {
        "width": {"magnitude": 3000000, "unit": "EMU"},
        "height": {"magnitude": 3000000, "unit": "EMU"}
      },
      "transform": {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": 311700,
        "translateY": 744575,
        "unit": "EMU"
      },
      "shape": {
        "shapeType": "TEXT_BOX",
        "text": {...}
      }
    }
  ],
  "slideProperties": {
    "layoutObjectId": "p1_l1",
    "masterObjectId": "p1_m",
    "notesPage": {
      "objectId": "g1234567890:notes",
      "pageType": "NOTES",
      "pageElements": [...]
    }
  },
  "pageProperties": {
    "pageBackgroundFill": {
      "solidFill": {
        "color": {
          "rgbColor": {"red": 1, "green": 1, "blue": 1}
        }
      }
    }
  }
}
```

## Inheritance Hierarchy

```
Master
  └── Layout (inherits from Master)
        └── Slide (inherits from Layout)
```

- Slides inherit page properties from their layout
- Layouts inherit page properties from their master
- Placeholder shapes inherit from parent placeholders

## Usage Examples

### Iterating Slides

```python
presentation = service.presentations().get(
    presentationId='presentation_id'
).execute()

for slide in presentation.get('slides', []):
    slide_id = slide['objectId']
    layout_id = slide.get('slideProperties', {}).get('layoutObjectId')

    for element in slide.get('pageElements', []):
        process_element(element)
```

### Getting a Specific Page

```python
page = service.presentations().pages().get(
    presentationId='presentation_id',
    pageObjectId='slide_id'
).execute()
```

### Creating a Slide

```python
requests = [{
    'createSlide': {
        'objectId': 'new_slide_id',
        'insertionIndex': 1,
        'slideLayoutReference': {
            'predefinedLayout': 'TITLE_AND_BODY'
        }
    }
}]
```

## Related Objects

- [PageElement](./page-element.md) - Elements on pages
- [Presentation](./presentation.md) - Parent container
- [Shape](./shape.md) - Shape elements

## Related Documentation

- [Create Slide Guide](../../guides/create-slide.md) - Creating slides
- [Page Elements Concept](../../concepts/page-elements.md) - Element types
