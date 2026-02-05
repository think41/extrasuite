# Merge Text Into a Document

The Google Docs API enables merging data from external sources into template documents. A template contains fixed text and placeholders for dynamic content—like a contract template with spaces for recipient details.

## Benefits of This Approach

- **Design flexibility**: Templates can be refined using the Google Docs editor rather than configuring parameters in code
- **Separation of concerns**: Content remains distinct from presentation, following established design principles

## Basic Recipe

1. Create a document with placeholder content for design and formatting purposes
2. Replace placeholders with tags unlikely to appear naturally (e.g., `{{account-holder-name}}`)
3. Use the Google Drive API to copy the template document (see @documents.md)
4. Use the Docs API's `batchUpdate()` method with `ReplaceAllTextRequest` to substitute values

Document IDs can be extracted from the URL format: `https://docs.google.com/document/d/documentId/edit`

## Code Examples

The following demonstrates replacing two fields across all tabs:

### Java

```java
String customerName = "Alice";
DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy/MM/dd");
String date = formatter.format(LocalDate.now());

List<Request> requests = new ArrayList<>();
requests.add(new Request()
    .setReplaceAllText(new ReplaceAllTextRequest()
        .setContainsText(new SubstringMatchCriteria()
            .setText("{{customer-name}}")
            .setMatchCase(true))
        .setReplaceText(customerName)));

requests.add(new Request()
    .setReplaceAllText(new ReplaceAllTextRequest()
        .setContainsText(new SubstringMatchCriteria()
            .setText("{{date}}")
            .setMatchCase(true))
        .setReplaceText(date)));

BatchUpdateDocumentRequest body = new BatchUpdateDocumentRequest().setRequests(requests);
BatchUpdateDocumentResponse response = docsService.documents()
    .batchUpdate(DOCUMENT_ID, body).execute();
```

### Node.js

```javascript
let customerName = 'Alice';
let date = new Date().toISOString().split('T')[0];

let requests = [
  {
    replaceAllText: {
      containsText: {
        text: '{{customer-name}}',
        matchCase: true,
      },
      replaceText: customerName,
    },
  },
  {
    replaceAllText: {
      containsText: {
        text: '{{date}}',
        matchCase: true,
      },
      replaceText: date,
    },
  },
];

let body = {requests};
let response = await docs.documents.batchUpdate({
  documentId: DOCUMENT_ID,
  requestBody: body,
});
```

### Python

```python
customer_name = 'Alice'
date = datetime.date.today().strftime('%Y/%m/%d')

requests = [
    {
        'replaceAllText': {
            'containsText': {
                'text': '{{customer-name}}',
                'matchCase': 'true'
            },
            'replaceText': customer_name,
        }
    },
    {
        'replaceAllText': {
            'containsText': {
                'text': '{{date}}',
                'matchCase': 'true'
            },
            'replaceText': date,
        }
    }
]

body = {'requests': requests}
response = service.documents().batchUpdate(documentId=DOCUMENT_ID, body=body).execute()
```

## Template Management

For application-owned templates, use a service account for creation. When generating document instances, use end-user credentials to ensure proper access control and prevent scaling issues.

### Creation Steps (with application credentials)

1. Create document via `documents.create`
2. Set read permissions for recipients
3. Set write permissions for template authors
4. Edit template as needed

### Instance Creation Steps (with user credentials)

1. Copy template using `files.copy`
2. Replace values using `documents.batchUpdate`

See @batch.md for grouping multiple replacement requests efficiently.
