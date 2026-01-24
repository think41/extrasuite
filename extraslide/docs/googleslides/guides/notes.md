# Speaker Notes

> **Source**: [Google Slides API - Notes](https://developers.google.com/workspace/slides/api/guides/notes)

## Overview

The Google Slides API enables developers to programmatically read and modify speaker notes in presentations through the notes pages system.

## Key Concepts

### Notes Pages

A notes page is a special page type used for generating handouts for slides. Each slide contains one notes page, with a BODY placeholder shape holding the speaker notes text.

### Notes Master

A presentation includes a single notes master that defines default elements and styling. **Important**: The notes master is entirely read-only via the API.

## Structure

```json
{
  "slide": {
    "objectId": "slide_id",
    "slideProperties": {
      "notesPage": {
        "objectId": "notes_page_id",
        "pageElements": [
          {
            "objectId": "notes_shape_id",
            "shape": {
              "shapeType": "TEXT_BOX",
              "placeholder": {
                "type": "BODY"
              },
              "text": {
                "textElements": [...]
              }
            }
          }
        ]
      }
    }
  }
}
```

## Reading Speaker Notes

### Step 1: Get the Slide

```http
GET https://slides.googleapis.com/v1/presentations/{presentationId}
```

### Step 2: Find the Notes Page

```python
# Python example
for slide in presentation.get('slides', []):
    notes_page = slide.get('slideProperties', {}).get('notesPage')
    if notes_page:
        # Find the BODY placeholder
        for element in notes_page.get('pageElements', []):
            shape = element.get('shape', {})
            placeholder = shape.get('placeholder', {})
            if placeholder.get('type') == 'BODY':
                speaker_notes_id = element.get('objectId')
                text_content = shape.get('text', {})
```

### Alternative: Use NotesProperties

The `NotesProperties` message contains a `speakerNotesObjectId` field:

```json
{
  "slideProperties": {
    "notesPage": {
      "notesProperties": {
        "speakerNotesObjectId": "notes_shape_id"
      }
    }
  }
}
```

**Note**: In rare cases, this object might not exist, meaning the slide has no speaker notes.

## Writing Speaker Notes

Use standard text manipulation requests on the speaker notes shape.

### Insert Text

```json
{
  "requests": [
    {
      "insertText": {
        "objectId": "notes_shape_id",
        "text": "Remember to mention the key benefits.\n\nTalk about the demo."
      }
    }
  ]
}
```

### Replace All Text

```json
{
  "requests": [
    {
      "deleteText": {
        "objectId": "notes_shape_id",
        "textRange": {"type": "ALL"}
      }
    },
    {
      "insertText": {
        "objectId": "notes_shape_id",
        "text": "New speaker notes content here."
      }
    }
  ]
}
```

### Auto-Creation

**Important**: In the rare case where the speaker notes shape doesn't exist, the Slides API creates it automatically when it receives a valid text operation.

## Limitations

| Operation | Supported |
|-----------|-----------|
| Read text content | ✓ |
| Write text content | ✓ |
| Modify text styling | ✓ |
| Modify shape properties | ✗ |
| Modify other notes page content | ✗ |
| Modify notes master | ✗ |

## Complete Example

### Reading Notes

```python
def get_speaker_notes(service, presentation_id, slide_id):
    presentation = service.presentations().get(
        presentationId=presentation_id
    ).execute()

    for slide in presentation.get('slides', []):
        if slide.get('objectId') == slide_id:
            notes_page = slide.get('slideProperties', {}).get('notesPage', {})
            for element in notes_page.get('pageElements', []):
                shape = element.get('shape', {})
                if shape.get('placeholder', {}).get('type') == 'BODY':
                    text_elements = shape.get('text', {}).get('textElements', [])
                    notes_text = ''
                    for elem in text_elements:
                        if 'textRun' in elem:
                            notes_text += elem['textRun'].get('content', '')
                    return notes_text
    return None
```

### Writing Notes

```python
def set_speaker_notes(service, presentation_id, notes_shape_id, new_text):
    requests = [
        {
            'deleteText': {
                'objectId': notes_shape_id,
                'textRange': {'type': 'ALL'}
            }
        },
        {
            'insertText': {
                'objectId': notes_shape_id,
                'text': new_text
            }
        }
    ]

    response = service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={'requests': requests}
    ).execute()

    return response
```

## Related Documentation

- [Text Structure](../concepts/text.md) - Text element model
- [Styling](./styling.md) - Text formatting
- [Presentations](./presentations.md) - Reading presentations
- [Page Elements](../concepts/page-elements.md) - Element types
