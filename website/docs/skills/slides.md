# Google Slides Skill

Create and edit Google Slides presentations using the declarative pull-edit-diff-push workflow with SML (Slide Markup Language).

!!! success "Status: Stable"
    This skill is fully supported for production use.

## Overview

The Google Slides skill enables your AI agent to:

- Pull presentations into editable SML (XML-based) files
- Modify text, shapes, positions, and styling
- Add and delete slides and elements
- Copy existing elements as templates
- Preview changes before applying
- Push edits back to Google Slides

All editing is declarative - the agent edits SML files, and ExtraSuite computes the minimal `batchUpdate` API calls to sync changes.

## The Workflow

```bash
# 1. Pull - download the presentation
uvx extraslide pull "https://docs.google.com/presentation/d/1abc.../edit"

# 2. Edit - modify the SML files in slides/

# 3. Diff - preview changes (dry run)
uvx extraslide diff ./1abc.../

# 4. Push - apply changes
uvx extraslide push ./1abc.../
```

## On-Disk Format

After `pull`, you'll have:

```
1abc.../
  presentation.json       # Metadata (title, ID, dimensions)
  id_mapping.json         # clean_id -> google_object_id mapping
  styles.json             # Styles for each element
  slides/
    01/content.sml        # Slide 1 content
    02/content.sml        # Slide 2 content
    ...
  .pristine/
    presentation.zip      # Original state for diff comparison
  .raw/
    presentation.json     # Raw API response
```

The agent edits `slides/NN/content.sml` files. When it runs `push`, ExtraSuite diffs the current SML against `.pristine/` and generates the minimal API update.

## SML Format

SML uses minimal XML to represent slides:

```xml
<Slide>
  <TextBox id="e1" x="100" y="50" w="500" h="80">
    <P><T>Quarterly Report</T></P>
  </TextBox>
  <Rect id="e2" x="50" y="200" w="300" h="150"/>
</Slide>
```

### Elements

| Element | Description |
|---------|-------------|
| `<TextBox>` | Text container with paragraphs |
| `<Rect>`, `<Ellipse>`, `<RoundRect>` | Basic shapes |
| `<Line>` | Lines and connectors |
| `<Image>` | Images |
| `<Table>` | Tables with `<Row>` and `<Cell>` |
| `<Group>` | Grouped elements |
| `<Video>` | Embedded videos |
| `<SheetsChart>` | Linked Google Sheets charts |

### Text Content

Text uses a paragraph (`<P>`) and text run (`<T>`) structure:

```xml
<TextBox id="e1" x="50" y="100" w="400" h="200">
  <P><T>Regular text </T><T>more text</T></P>
  <P><T>Second paragraph</T></P>
</TextBox>
```

### Positions and Sizes

All positions (`x`, `y`) and sizes (`w`, `h`) are in points:

```xml
<Rect id="e1" x="100" y="200" w="300" h="150"/>
```

### Copying Elements

To copy an element, duplicate its XML with the same `id`, new position, and **omit `w` and `h`**:

```xml
<!-- Original -->
<Rect id="e1" x="100" y="100" w="200" h="100"/>

<!-- Copy (omit w/h to signal copy) -->
<Rect id="e1" x="400" y="100"/>
```

## Common Edits

### Change text

```xml
<!-- Before -->
<P><T>Old heading</T></P>
<!-- After -->
<P><T>New heading</T></P>
```

### Move or resize

```xml
<!-- Before -->
<TextBox id="e1" x="72" y="144" w="400" h="50">
<!-- After -->
<TextBox id="e1" x="150" y="144" w="500" h="50">
```

### Add/delete elements

Add new XML elements or remove existing ones. The diff engine computes the necessary API calls.

## Best Practices

1. **Always pull fresh before editing** - SML becomes stale after push
2. **Preview with diff before push** - Verify changes are correct
3. **Don't modify `id` or `range` attributes** - They're internal references
4. **Use explicit `<P><T>` structure** - Never bare text
5. **Keep edits minimal** - Only change what's necessary

## Limitations

- Complex animations not supported
- Limited chart creation (linked charts are read-only)
- Some layout options unavailable

---

**Related:**

- [Google Sheets Skill](sheets.md) - For spreadsheet operations
- [Google Docs Skill](docs.md) - For document operations
- [Google Forms Skill](forms.md) - For form operations
