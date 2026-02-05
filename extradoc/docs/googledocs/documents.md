# Create and Manage Documents

This documentation covers fundamental tasks for working with Google Docs documents, including creation and duplication operations.

## Create a Blank Document

To create a new document, use the `documents.create` method on the documents collection.

### Java

```java
private static void createDoc(Docs service) throws IOException {
    Document doc = new Document()
            .setTitle("My Document");
    doc = service.documents().create(doc)
            .execute();
    System.out.println("Created document with title: " + doc.getTitle());
}
```

### Python

```python
title = 'My Document'
body = {
    'title': title
}
doc = service.documents().create(body=body).execute()
print('Created document with title: {0}'.format(doc.get('title')))
```

### PHP

```php
$title = 'My Document';
$document = new Google_Service_Docs_Document(array(
    'title' => $title
));
$document = $service->documents->create($document);
printf("Created document with title: %s\n", $document->title);
```

## Working with Google Drive Folders

By default, newly created documents are saved to the user's root Drive folder. To save documents to specific folders, two approaches are available:

1. **Move after creation**: Use Drive API's `files.update` method to move the document post-creation
2. **Create in folder directly**: Use Drive API's `files.create` method with `application/vnd.google-apps.document` as the MIME type

Both alternatives require appropriate Drive API scopes for authorization.

## Copy an Existing Document

To duplicate a document, use Drive API's `files.copy` method.

### Java

```java
String copyTitle = "Copy Title";
File copyMetadata = new File().setName(copyTitle);
File documentCopyFile = driveService.files().copy(documentId, copyMetadata).execute();
String documentCopyId = documentCopyFile.getId();
```

### Python

```python
copy_title = 'Copy Title'
body = {
    'name': copy_title
}
drive_response = drive_service.files().copy(
    fileId=document_id, body=body).execute()
document_copy_id = drive_response.get('id')
```

Document IDs can be found in the document URL at: `https://docs.google.com/document/d/DOCUMENT_ID/edit`

Authorization requires appropriate Drive API scopes.

See @merge.md for using document copies as templates.
