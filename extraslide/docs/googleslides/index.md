# Google Slides API Documentation

This documentation is designed to help developers understand the Google Slides API in the context of building the **extraslide** library - a Python library that simplifies editing Google Slides through an HTML-like abstraction.

## extraslide Workflow

The library implements this workflow:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Google Slides  │────▶│  HTML-like       │────▶│  Modified       │
│  (JSON via API) │     │  Representation  │     │  Representation │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                                                │
        │                                                ▼
        │                                       ┌─────────────────┐
        │                                       │  Diff Engine    │
        │                                       │  (Intentions)   │
        │                                       └─────────────────┘
        │                                                │
        ▼                                                ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Updated        │◀────│  batchUpdate     │◀────│  Reconciler     │
│  Google Slides  │     │  Requests        │     │  (Optimized)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

1. **Read**: Fetch presentation using `presentations.get`
2. **Convert**: Transform JSON into HTML-like representation
3. **Modify**: Authors/editors modify the HTML representation
4. **Diff**: Compare original and modified to understand intentions
5. **Reconcile**: Generate optimized `batchUpdate` requests

## Documentation Structure

```
docs/googleslides/
├── index.md                    # This file
├── guides/                     # How-to guides
│   ├── overview.md             # API overview and architecture
│   ├── presentations.md        # Creating and managing presentations
│   ├── create-slide.md         # Adding slides
│   ├── add-shape.md            # Adding shapes and text
│   ├── add-image.md            # Adding images
│   ├── add-chart.md            # Adding charts from Sheets
│   ├── transform.md            # Positioning and sizing elements
│   ├── styling.md              # Text and shape styling
│   ├── merge.md                # Mail merge functionality
│   ├── notes.md                # Speaker notes
│   ├── field-masks.md          # Efficient partial updates
│   ├── batch.md                # Batch update patterns
│   └── performance.md          # Optimization tips
├── concepts/                   # Core concepts
│   ├── page-elements.md        # Understanding page elements
│   ├── text.md                 # Text structure and styling
│   └── transforms.md           # Affine transforms explained
└── reference/                  # API reference
    ├── rest-api.md             # REST endpoints
    ├── discovery.json          # Service discovery document
    ├── objects/                # Data object documentation
    │   ├── index.md            # Object type overview
    │   ├── presentation.md     # Presentation object
    │   ├── page.md             # Page object
    │   ├── page-element.md     # PageElement object
    │   ├── shape.md            # Shape object
    │   ├── affine-transform.md # AffineTransform object
    │   └── text-content.md     # TextContent object
    └── requests/               # BatchUpdate request types
        ├── index.md            # Request type overview
        ├── create-shape.md     # CreateShapeRequest
        ├── insert-text.md      # InsertTextRequest
        ├── update-text-style.md # UpdateTextStyleRequest
        ├── delete-object.md    # DeleteObjectRequest
        └── update-transform.md # UpdatePageElementTransformRequest
```

## Quick Start

### Reading a Presentation

```python
from googleapiclient.discovery import build

service = build('slides', 'v1', credentials=credentials)

# Get full presentation
presentation = service.presentations().get(
    presentationId='presentation_id'
).execute()

# Access slides
for slide in presentation.get('slides', []):
    slide_id = slide['objectId']
    for element in slide.get('pageElements', []):
        if 'shape' in element:
            text = element['shape'].get('text', {})
            # Process text content
```

### Modifying a Presentation

```python
requests = [
    # Create a slide
    {
        'createSlide': {
            'objectId': 'new_slide',
            'insertionIndex': 1
        }
    },
    # Add a text box
    {
        'createShape': {
            'objectId': 'text_box',
            'shapeType': 'TEXT_BOX',
            'elementProperties': {
                'pageObjectId': 'new_slide',
                'size': {
                    'width': {'magnitude': 5000000, 'unit': 'EMU'},
                    'height': {'magnitude': 1000000, 'unit': 'EMU'}
                },
                'transform': {
                    'scaleX': 1, 'scaleY': 1,
                    'translateX': 2000000, 'translateY': 2000000,
                    'unit': 'EMU'
                }
            }
        }
    },
    # Insert text
    {
        'insertText': {
            'objectId': 'text_box',
            'text': 'Hello, World!'
        }
    }
]

response = service.presentations().batchUpdate(
    presentationId='presentation_id',
    body={'requests': requests}
).execute()
```

## Key Concepts for extraslide

### 1. Object IDs
Every element has a unique `objectId`. extraslide must:
- Track object IDs when reading
- Generate unique IDs when creating
- Map HTML elements to object IDs for updates

### 2. Atomic Batch Updates
All modifications happen through `batchUpdate`:
- All requests succeed or all fail
- Requests execute in order
- Later requests can reference earlier-created objects

### 3. Field Masks
Partial updates require field masks:
- Only specified fields are modified
- Unspecified fields retain current values
- Essential for efficient reconciliation

### 4. Transform Calculations
Position and size use affine transforms:
- EMU units (914,400 per inch)
- Visual size = transform × built-in size
- Upper-left corner positioning

### 5. Text Structure
Text is a sequence of elements:
- ParagraphMarker (paragraph boundaries)
- TextRun (styled text spans)
- Indexed by character position

## Navigation

| Section | Purpose |
|---------|---------|
| [Guides](./guides/overview.md) | Step-by-step instructions |
| [Concepts](./concepts/page-elements.md) | Understanding the data model |
| [Reference](./reference/rest-api.md) | Complete API details |

## External Resources

- [Official Google Slides API Documentation](https://developers.google.com/workspace/slides/api)
- [API Explorer](https://developers.google.com/workspace/slides/api/reference/rest)
- [Quota and Limits](https://developers.google.com/workspace/slides/limits)
