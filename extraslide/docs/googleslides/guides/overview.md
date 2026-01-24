# Google Slides API Overview

> **Source**: [Google Slides API Overview](https://developers.google.com/workspace/slides/api/guides/overview)

## Purpose and Capabilities

The Google Slides API enables developers to create and modify Google Slides presentations programmatically. Applications can leverage this API to generate presentation decks automatically from data sources, combining customer information with pre-designed templates to produce finished slides faster than manual creation.

## Core Architecture

### Presentation Structure

A presentation comprises:
- **Pages**: Including slides, masters, layouts, notes pages, and notes masters
- **Page Elements**: Visual components placed on pages such as shapes, images, videos, lines, tables, WordArt, and charts

The presentation ID can be extracted from the Google Slides URL using the regex pattern:
```
/presentation/d/([a-zA-Z0-9-_]+)
```

### Page Types

| Type | Description |
|------|-------------|
| **Slides** | Content pages presented to audiences |
| **Masters** | Define default styles and elements across all slides using that master |
| **Layouts** | Templates for arranging page elements on slides |
| **Notes Pages** | Handout content with speaker notes (read-only via API) |

## Working with the API

### Reading Presentations

Use `presentations.get` to retrieve the full JSON representation of a presentation:

```
GET https://slides.googleapis.com/v1/presentations/{presentationId}
```

This returns the complete presentation structure including all pages, page elements, and their properties.

### Batch Updates

The primary modification method is `batchUpdate()`, which accepts multiple Request objects to perform operations like:
- Creating and managing slides
- Adding elements (shapes, tables, images)
- Manipulating text content
- Applying transforms to elements
- Reordering slides

**Key feature**: Batching ensures atomicity—if one request fails, no changes are written.

```
POST https://slides.googleapis.com/v1/presentations/{presentationId}:batchUpdate
```

### Object ID Management

When creating objects, developers can specify optional object IDs (5-50 characters, starting with alphanumeric or underscore).

**Important**: You cannot depend on an object ID being unchanged after a presentation is changed in the Slides UI. For long-term stability, track objects by text content or alt-text.

## Request Categories

The API supports specialized requests for:

| Category | Operations |
|----------|------------|
| **Slides** | Create, duplicate, delete, reorder |
| **Page Elements** | Shapes, lines, transforms |
| **Tables** | Rows, columns, cells, borders |
| **Charts** | Creation, refresh, replacement |
| **Media** | Images, videos, properties |
| **Text** | Insert, delete, replace, styling |

## Workflow for extraslide Library

The extraslide library implements this workflow:

1. **Read**: Fetch presentation using `presentations.get`
2. **Convert**: Transform JSON into HTML-like representation
3. **Modify**: Allow authors/editors to modify the HTML representation
4. **Diff**: Compare original and modified states to understand intentions
5. **Reconcile**: Generate optimized `batchUpdate` requests to apply changes

## Related Documentation

- [Page Elements](../concepts/page-elements.md) - Understanding page element types
- [Text Structure](../concepts/text.md) - Working with text content
- [Transforms](../concepts/transforms.md) - Positioning and scaling elements
- [Batch Updates](./batch.md) - Efficient API usage patterns
- [REST API Reference](../reference/rest-api.md) - Complete API endpoints
