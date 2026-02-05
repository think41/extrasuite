# Working with Tables

The Google Docs API enables you to programmatically manipulate table structures and content. You can perform operations including inserting/deleting rows, columns, or entire tables; adding content to cells; reading cell contents; and modifying column properties and row styles.

Tables are represented as `StructuralElement` objects containing a list of `tableRows`, each with `tableCells`. Every table has start and end indexes indicating its document position.

See @structure.md for understanding how tables fit into document structure.

## Inserting Tables

Use `InsertTableRequest` to add a new table by specifying:
- Dimensions (rows and columns)
- Location (index or end of segment with tab ID)

### Java

```java
List<Request> requests = new ArrayList<>();
requests.add(new Request().setInsertTable(
    new InsertTableRequest()
        .setEndOfSegmentLocation(new EndOfSegmentLocation().setTabId(TAB_ID))
        .setRows(3)
        .setColumns(3)));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Python

```python
requests = [{
    'insertTable': {
        'rows': 3,
        'columns': 3,
        'endOfSegmentLocation': {
            'segmentId': '',
            'tabId': TAB_ID
        }
    },
}]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

## Deleting Tables

To remove a table, use `DeleteContentRangeRequest` with the table's start and end indexes.

```python
requests = [{
    'deleteContentRange': {
        'range': {
            'startIndex': TABLE_START_INDEX,
            'endIndex': TABLE_END_INDEX,
            'tabId': TAB_ID
        }
    }
}]
```

## Managing Rows

### Inserting Rows

Use `InsertTableRowRequest` to add rows above or below a specified cell location.

```python
requests = [{
    'insertTableRow': {
        'tableCellLocation': {
            'tableStartLocation': {'index': TABLE_START_INDEX, 'tabId': TAB_ID},
            'rowIndex': 1,
            'columnIndex': 1
        },
        'insertBelow': True
    }
}]
```

### Deleting Rows

Use `DeleteTableRowRequest` to remove a row.

```python
requests = [{
    'deleteTableRow': {
        'tableCellLocation': {
            'tableStartLocation': {'index': TABLE_START_INDEX, 'tabId': TAB_ID},
            'rowIndex': 1,
            'columnIndex': 1
        }
    }
}]
```

## Managing Columns

### Inserting Columns

Use `InsertTableColumnRequest`, specifying the target cell and insertion direction (left or right).

```python
requests = [{
    'insertTableColumn': {
        'tableCellLocation': {
            'tableStartLocation': {'index': TABLE_START_INDEX, 'tabId': TAB_ID},
            'rowIndex': 1,
            'columnIndex': 1
        },
        'insertRight': True
    }
}]
```

### Deleting Columns

Use `DeleteTableColumnRequest` to remove a column.

```python
requests = [{
    'deleteTableColumn': {
        'tableCellLocation': {
            'tableStartLocation': {'index': TABLE_START_INDEX, 'tabId': TAB_ID},
            'rowIndex': 1,
            'columnIndex': 1
        }
    }
}]
```

## Reading and Writing Cell Content

Read cell contents by recursively inspecting structural elements within cells. Write to cells using `InsertTextRequest` with an index within the target cell. Delete cell text with `DeleteContentRangeRequest`.

See @move-text.md for text insertion and deletion details.

## Modifying Properties

### Column Properties

`UpdateTableColumnPropertiesRequest` modifies column widths and other properties. Provide the table's starting index and `TableColumnProperties` object.

```python
requests = [{
    'updateTableColumnProperties': {
        'tableStartLocation': {'index': TABLE_START_INDEX, 'tabId': TAB_ID},
        'columnIndices': [0, 2],
        'tableColumnProperties': {
            'widthType': 'FIXED_WIDTH',
            'width': {'magnitude': 100, 'unit': 'PT'}
        },
        'fields': 'widthType,width'
    }
}]
```

### Row Styles

`UpdateTableRowStyleRequest` adjusts row-level styling like minimum height using `TableRowStyle` objects.

```python
requests = [{
    'updateTableRowStyle': {
        'tableStartLocation': {'index': TABLE_START_INDEX, 'tabId': TAB_ID},
        'rowIndices': [0],
        'tableRowStyle': {
            'minRowHeight': {'magnitude': 30, 'unit': 'PT'}
        },
        'fields': 'minRowHeight'
    }
}]
```

See @field-masks.md for details on the `fields` parameter.
