# Google Slides API Requests

This section documents the request types used with the `batchUpdate` API.

## Usage

All requests are sent via the `presentations.batchUpdate` endpoint:

```json
POST https://slides.googleapis.com/v1/presentations/{presentationId}:batchUpdate

{
  "requests": [
    { /* request 1 */ },
    { /* request 2 */ }
  ]
}
```

## Create Requests

- [CreateImageRequest](./create-image.md)
- [CreateLineRequest](./create-line.md)
- [CreateParagraphBulletsRequest](./create-paragraph-bullets.md)
- [CreateShapeRequest](./create-shape.md)
- [CreateSheetsChartRequest](./create-sheets-chart.md)
- [CreateSlideRequest](./create-slide.md)
- [CreateTableRequest](./create-table.md)
- [CreateVideoRequest](./create-video.md)

## Update Requests

- [UpdateImagePropertiesRequest](./update-image-properties.md)
- [UpdateLineCategoryRequest](./update-line-category.md)
- [UpdateLinePropertiesRequest](./update-line-properties.md)
- [UpdatePageElementAltTextRequest](./update-page-element-alt-text.md)
- [UpdatePageElementTransformRequest](./update-page-element-transform.md)
- [UpdatePageElementsZOrderRequest](./update-page-elements-z-order.md)
- [UpdatePagePropertiesRequest](./update-page-properties.md)
- [UpdateParagraphStyleRequest](./update-paragraph-style.md)
- [UpdateShapePropertiesRequest](./update-shape-properties.md)
- [UpdateSlidePropertiesRequest](./update-slide-properties.md)
- [UpdateSlidesPositionRequest](./update-slides-position.md)
- [UpdateTableBorderPropertiesRequest](./update-table-border-properties.md)
- [UpdateTableCellPropertiesRequest](./update-table-cell-properties.md)
- [UpdateTableColumnPropertiesRequest](./update-table-column-properties.md)
- [UpdateTableRowPropertiesRequest](./update-table-row-properties.md)
- [UpdateTextStyleRequest](./update-text-style.md)
- [UpdateVideoPropertiesRequest](./update-video-properties.md)

## Delete Requests

- [DeleteObjectRequest](./delete-object.md)
- [DeleteParagraphBulletsRequest](./delete-paragraph-bullets.md)
- [DeleteTableColumnRequest](./delete-table-column.md)
- [DeleteTableRowRequest](./delete-table-row.md)
- [DeleteTextRequest](./delete-text.md)

## Insert Requests

- [InsertTableColumnsRequest](./insert-table-columns.md)
- [InsertTableRowsRequest](./insert-table-rows.md)
- [InsertTextRequest](./insert-text.md)

## Replace Requests

- [ReplaceAllShapesWithImageRequest](./replace-all-shapes-with-image.md)
- [ReplaceAllShapesWithSheetsChartRequest](./replace-all-shapes-with-sheets-chart.md)
- [ReplaceAllTextRequest](./replace-all-text.md)
- [ReplaceImageRequest](./replace-image.md)

## Other Requests

- [DuplicateObjectRequest](./duplicate-object.md)
- [GroupObjectsRequest](./group-objects.md)
- [MergeTableCellsRequest](./merge-table-cells.md)
- [RefreshSheetsChartRequest](./refresh-sheets-chart.md)
- [RerouteLineRequest](./reroute-line.md)
- [UngroupObjectsRequest](./ungroup-objects.md)
- [UnmergeTableCellsRequest](./unmerge-table-cells.md)

