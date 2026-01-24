# Line

A PageElement kind representing a non-connector line, straight connector, curved connector, or bent connector.

## Schema

```json
{
  "lineProperties": [LineProperties],
  "lineType": string,
  "lineCategory": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `lineProperties` | [LineProperties] | The properties of the line. |
| `lineType` | string | The type of the line. |
| `lineCategory` | string | The category of the line. It matches the `category` specified in CreateLineRequest, and can be up... |

### lineType Values

| Value | Description |
|-------|-------------|
| `TYPE_UNSPECIFIED` | An unspecified line type. |
| `STRAIGHT_CONNECTOR_1` | Straight connector 1 form. Corresponds to ECMA-376 ST_ShapeType 'straightConnector1'. |
| `BENT_CONNECTOR_2` | Bent connector 2 form. Corresponds to ECMA-376 ST_ShapeType 'bentConnector2'. |
| `BENT_CONNECTOR_3` | Bent connector 3 form. Corresponds to ECMA-376 ST_ShapeType 'bentConnector3'. |
| `BENT_CONNECTOR_4` | Bent connector 4 form. Corresponds to ECMA-376 ST_ShapeType 'bentConnector4'. |
| `BENT_CONNECTOR_5` | Bent connector 5 form. Corresponds to ECMA-376 ST_ShapeType 'bentConnector5'. |
| `CURVED_CONNECTOR_2` | Curved connector 2 form. Corresponds to ECMA-376 ST_ShapeType 'curvedConnector2'. |
| `CURVED_CONNECTOR_3` | Curved connector 3 form. Corresponds to ECMA-376 ST_ShapeType 'curvedConnector3'. |
| `CURVED_CONNECTOR_4` | Curved connector 4 form. Corresponds to ECMA-376 ST_ShapeType 'curvedConnector4'. |
| `CURVED_CONNECTOR_5` | Curved connector 5 form. Corresponds to ECMA-376 ST_ShapeType 'curvedConnector5'. |
| `STRAIGHT_LINE` | Straight line. Corresponds to ECMA-376 ST_ShapeType 'line'. This line type is not a connector. |

### lineCategory Values

| Value | Description |
|-------|-------------|
| `LINE_CATEGORY_UNSPECIFIED` | Unspecified line category. |
| `STRAIGHT` | Straight connectors, including straight connector 1. |
| `BENT` | Bent connectors, including bent connector 2 to 5. |
| `CURVED` | Curved connectors, including curved connector 2 to 5. |

## Related Objects

- [LineProperties](./line-properties.md)

