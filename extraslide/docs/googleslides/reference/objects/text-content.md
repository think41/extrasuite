# TextContent

Container for text content within shapes and table cells.

## Schema

```json
{
  "textElements": [TextElement],
  "lists": {
    "listId": List
  }
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `textElements` | TextElement[] | Ordered list of text elements (read-only) |
| `lists` | Map<string, List> | Bulleted lists, keyed by list ID |

## TextElement Types

### ParagraphMarker

Marks the start of a paragraph:

```json
{
  "startIndex": 0,
  "endIndex": 25,
  "paragraphMarker": {
    "style": {
      "alignment": "START",
      "lineSpacing": 100,
      "indentStart": {"magnitude": 0, "unit": "PT"},
      "indentEnd": {"magnitude": 0, "unit": "PT"},
      "spaceAbove": {"magnitude": 0, "unit": "PT"},
      "spaceBelow": {"magnitude": 0, "unit": "PT"},
      "indentFirstLine": {"magnitude": 0, "unit": "PT"},
      "direction": "LEFT_TO_RIGHT"
    },
    "bullet": {
      "listId": "list123",
      "nestingLevel": 0,
      "glyph": "•",
      "bulletStyle": {...}
    }
  }
}
```

### TextRun

A contiguous string with uniform styling:

```json
{
  "startIndex": 0,
  "endIndex": 11,
  "textRun": {
    "content": "Hello World",
    "style": {
      "bold": false,
      "italic": false,
      "underline": false,
      "strikethrough": false,
      "smallCaps": false,
      "fontFamily": "Arial",
      "fontSize": {"magnitude": 18, "unit": "PT"},
      "foregroundColor": {
        "opaqueColor": {
          "rgbColor": {"red": 0, "green": 0, "blue": 0}
        }
      },
      "backgroundColor": {...},
      "link": {"url": "https://..."},
      "baselineOffset": "NONE"
    }
  }
}
```

### AutoText

Dynamic text like slide numbers:

```json
{
  "startIndex": 0,
  "endIndex": 1,
  "autoText": {
    "type": "SLIDE_NUMBER",
    "content": "3"
  }
}
```

AutoText types:
- `SLIDE_NUMBER` - Current slide number

## List

Defines a bulleted or numbered list:

```json
{
  "listId": "list123",
  "nestingLevel": {
    "0": {
      "bulletStyle": {
        "foregroundColor": {...},
        "fontSize": {...}
      }
    },
    "1": {
      "bulletStyle": {...}
    }
  }
}
```

## Example: Complete TextContent

```json
{
  "textElements": [
    {
      "startIndex": 0,
      "endIndex": 13,
      "paragraphMarker": {
        "style": {
          "alignment": "START"
        }
      }
    },
    {
      "startIndex": 0,
      "endIndex": 5,
      "textRun": {
        "content": "Hello",
        "style": {
          "bold": true,
          "fontSize": {"magnitude": 24, "unit": "PT"}
        }
      }
    },
    {
      "startIndex": 5,
      "endIndex": 6,
      "textRun": {
        "content": " ",
        "style": {
          "fontSize": {"magnitude": 24, "unit": "PT"}
        }
      }
    },
    {
      "startIndex": 6,
      "endIndex": 12,
      "textRun": {
        "content": "World!",
        "style": {
          "italic": true,
          "fontSize": {"magnitude": 24, "unit": "PT"}
        }
      }
    },
    {
      "startIndex": 12,
      "endIndex": 13,
      "textRun": {
        "content": "\n",
        "style": {}
      }
    }
  ],
  "lists": {}
}
```

## Example: Bulleted List

```json
{
  "textElements": [
    {
      "startIndex": 0,
      "endIndex": 7,
      "paragraphMarker": {
        "style": {"alignment": "START"},
        "bullet": {
          "listId": "list1",
          "nestingLevel": 0,
          "glyph": "•"
        }
      }
    },
    {
      "startIndex": 0,
      "endIndex": 6,
      "textRun": {"content": "Item 1", "style": {}}
    },
    {
      "startIndex": 6,
      "endIndex": 7,
      "textRun": {"content": "\n", "style": {}}
    },
    {
      "startIndex": 7,
      "endIndex": 14,
      "paragraphMarker": {
        "style": {"alignment": "START"},
        "bullet": {
          "listId": "list1",
          "nestingLevel": 0,
          "glyph": "•"
        }
      }
    },
    {
      "startIndex": 7,
      "endIndex": 13,
      "textRun": {"content": "Item 2", "style": {}}
    },
    {
      "startIndex": 13,
      "endIndex": 14,
      "textRun": {"content": "\n", "style": {}}
    }
  ],
  "lists": {
    "list1": {
      "listId": "list1",
      "nestingLevel": {
        "0": {"bulletStyle": {}}
      }
    }
  }
}
```

## Extracting Plain Text

```python
def extract_text(text_content):
    """Extract plain text from TextContent."""
    text = ''
    for element in text_content.get('textElements', []):
        if 'textRun' in element:
            text += element['textRun'].get('content', '')
        elif 'autoText' in element:
            text += element['autoText'].get('content', '')
    return text
```

## Extracting Styled Runs

```python
def extract_styled_runs(text_content):
    """Extract text runs with their styles."""
    runs = []
    for element in text_content.get('textElements', []):
        if 'textRun' in element:
            runs.append({
                'text': element['textRun'].get('content', ''),
                'style': element['textRun'].get('style', {}),
                'start': element.get('startIndex', 0),
                'end': element.get('endIndex', 0)
            })
    return runs
```

## Related Objects

- [TextStyle](./text-style.md) - Character formatting
- [ParagraphStyle](./paragraph-style.md) - Paragraph formatting
- [Shape](./shape.md) - Parent container

## Related Documentation

- [Text Concept](../../concepts/text.md) - Text structure overview
- [Styling Guide](../../guides/styling.md) - Text formatting
