# Page Elements

> **Source**: [Google Slides API - Page Elements](https://developers.google.com/workspace/slides/api/concepts/page-elements)

## Architecture Overview

Google Slides presentations follow a hierarchical structure:

```
Presentation
└── Pages (slides, masters, layouts, notes)
    └── Page Elements (shapes, images, tables, etc.)
```

- **Presentation**: The outermost container saved in Google Drive
- **Pages**: Various types including slides, masters, layouts, and notes pages
- **Page Elements**: Visual components that compose page content

## Page Types

| Type | Description |
|------|-------------|
| **Slides** | User-visible pages in presentations |
| **Masters** | Define default text styles and backgrounds for all derived slides |
| **Layouts** | Templates determining content arrangement for specific slide types |
| **Notes Pages** | Primarily for speaker notes functionality |
| **Notes Masters** | Define default styling for notes pages |

## Page Element Types

The API defines eight distinct page element kinds:

| Element | Purpose | Update Request |
|---------|---------|----------------|
| **Shape** | Visual objects (rectangles, ellipses, text boxes) | `UpdateShapePropertiesRequest` |
| **Image** | Imported graphics | `UpdateImagePropertiesRequest` |
| **Video** | Imported video content | `UpdateVideoPropertiesRequest` |
| **Line** | Visual lines, curves, connectors | `UpdateLinePropertiesRequest` |
| **Table** | Content grids | `UpdateTableCellPropertiesRequest` |
| **WordArt** | Text-based visual elements | (part of Shape) |
| **SheetsChart** | Charts from Google Sheets | `RefreshSheetsChartRequest` |
| **Group** | Multiple elements treated as a single unit | `UngroupObjectsRequest` |

## JSON Structure

Pages contain this structure:

```json
{
  "pageElements": [
    {
      "objectId": "element_id_here",
      "size": {
        "width": {"magnitude": 3000000, "unit": "EMU"},
        "height": {"magnitude": 3000000, "unit": "EMU"}
      },
      "transform": {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": 100000,
        "translateY": 100000,
        "unit": "EMU"
      },
      "shape": { ... }  // or "image", "table", "line", etc.
    }
  ]
}
```

## Common Properties

All page elements share these properties:

| Property | Description |
|----------|-------------|
| `objectId` | Unique identifier for the element |
| `size` | Built-in dimensions (width and height) |
| `transform` | Affine transform matrix for positioning/scaling |
| `title` | Accessible title (for screen readers) |
| `description` | Accessible description |

## Element-Specific Properties

### Shape Properties
- `shapeType`: The type of shape (TEXT_BOX, RECTANGLE, etc.)
- `text`: Text content within the shape
- `shapeProperties`: Fill, outline, shadow, link

### Image Properties
- `contentUrl`: Source URL of the image
- `imageProperties`: Outline, shadow, recolor, brightness, contrast

### Table Properties
- `rows`: Number of rows
- `columns`: Number of columns
- `tableRows`: Array of row data with cells
- `tableColumns`: Column width definitions

### Line Properties
- `lineType`: STRAIGHT_LINE, BENT_CONNECTOR, CURVED_CONNECTOR
- `lineProperties`: Start/end arrow, dash style, weight

## Property Categories

Common properties across elements include:

| Category | Description |
|----------|-------------|
| **Color** | RGB values or theme color references |
| **Fill** | Interior rendering (commonly solid colors) |
| **Outline** | Surrounding lines with configurable width/dash style |
| **Shadow** | Visual effects (read-only via API) |

## Property Inheritance

Two inheritance mechanisms exist:

### 1. Page Properties
- Slides inherit from layouts
- Layouts inherit from masters

### 2. Shape Properties
- Placeholder shapes inherit from parent placeholders via `parentObjectId`
- Objects inherit properties by omitting values, allowing parent defaults to apply

The `PropertyState` enumeration controls whether properties render or inherit-only:
- `RENDERED`: Property is rendered on the element
- `NOT_RENDERED`: Property is not rendered
- `INHERIT`: Property inherits from parent

## Updates and Field Masks

Use `batchUpdate()` calls with appropriate `Update...Properties` requests:

```json
{
  "requests": [{
    "updateShapeProperties": {
      "objectId": "shape_id",
      "shapeProperties": {
        "shapeBackgroundFill": {
          "solidFill": {
            "color": {"rgbColor": {"red": 1, "green": 0, "blue": 0}}
          }
        }
      },
      "fields": "shapeBackgroundFill.solidFill.color"
    }
  }]
}
```

**Best Practice**: Always specify exact fields in field masks rather than using wildcards (`*`), as future API updates might introduce unintended errors.

## Related Documentation

- [Overview](../guides/overview.md) - API overview and architecture
- [Transforms](./transforms.md) - Positioning and scaling elements
- [Text Structure](./text.md) - Working with text in shapes
- [Add Shape Guide](../guides/add-shape.md) - Creating shapes
- [Field Masks](../guides/field-masks.md) - Efficient updates
