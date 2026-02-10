# Sharing Documents

Learn how to share your Google documents with your AI agent and manage permissions effectively.

## How Sharing Works

ExtraSuite uses Google's standard sharing model. Your AI agent has a **service account email** that works just like a regular Google account. When you share a document with this email, your agent can access it.

```
yourname-domain@project.iam.gserviceaccount.com
```

!!! important "No Automatic Access"
    Your AI agent cannot access any document unless you explicitly share it. This is a security feature, not a limitation.

## Finding Your Service Account Email

1. Go to [extrasuite.think41.com](https://extrasuite.think41.com)
2. Sign in with your Google account
3. Your service account email is displayed in **Step 2**
4. Click **Copy Email** to copy it to your clipboard

## Sharing a Document

### Via Google Workspace UI

1. Open your Google Sheet, Doc, Slide, or Form
2. Click the **Share** button (top right)
3. In the "Add people and groups" field, paste your service account email
4. Choose permission level:
   - **Viewer** - Read-only access
   - **Commenter** - Can add comments
   - **Editor** - Full read/write access
5. Click **Send** (no notification will be sent to the service account)

### Via Google Drive

1. Open [Google Drive](https://drive.google.com)
2. Right-click the file or folder
3. Select **Share** > **Share**
4. Add your service account email
5. Set permissions and click **Done**

### Sharing a Folder

To share multiple documents at once:

1. Create a folder in Google Drive
2. Move your files into the folder
3. Share the folder with your service account email
4. All documents in the folder will be accessible

!!! tip "Folder Sharing"
    Sharing a folder is more efficient if you work with many related documents. The agent will have access to everything in the folder.

## Permission Levels Explained

### Viewer (Read-Only)

Your agent can:

- Read all data in the spreadsheet
- Download/export data
- View formulas

Your agent cannot:

- Make any changes
- Add comments
- Modify formatting

**Best for**: Analysis tasks, data extraction, read-only reports

### Commenter

Your agent can:

- Everything a Viewer can do
- Add comments to cells
- Reply to existing comments

Your agent cannot:

- Modify cell contents
- Change formatting
- Add/delete sheets

**Best for**: Review workflows, collaborative feedback

### Editor

Your agent can:

- Full read and write access
- Modify cell contents and formulas
- Add, rename, delete sheets
- Change formatting
- Add charts and images

**Best for**: Data entry, report generation, automated updates

## Best Practices

### 1. Start with Viewer Access

Grant Viewer access first to let your agent analyze the data. Only upgrade to Editor when you're ready for modifications.

### 2. Use Dedicated Sheets

For automated workflows, create dedicated spreadsheets rather than sharing important production data.

### 3. Make Backups

Before granting Editor access to important spreadsheets:

1. File > Make a copy
2. Keep the copy as a backup
3. Share the original with your agent

### 4. Use Folder Organization

```
My AI Workflows/
├── Input Data/          (Viewer access)
├── Working Files/       (Editor access)
└── Output Reports/      (Editor access)
```

### 5. Descriptive Naming

Name your spreadsheets clearly so your AI agent (and you) can easily identify them:

```
Q4-2024-Sales-Analysis (not "Sheet1 copy")
Customer-Retention-Dashboard (not "Data")
```

## Verifying Access

### Test with the Verification Script

```bash
~/.claude/skills/gsheets/venv/bin/python ~/.claude/skills/gsheets/verify_access.py <spreadsheet-url>
```

This will confirm:

- ✅ Authentication is working
- ✅ Spreadsheet is accessible
- ✅ Permission level

### Test with a Simple Prompt

Ask your AI agent:

```
Read the first 5 rows from https://docs.google.com/spreadsheets/d/abc123/edit
```

If it works, sharing is correctly configured.

## Common Sharing Scenarios

### Personal Spreadsheets

Share individual spreadsheets directly with your service account email.

### Team Spreadsheets

1. Check with your team before sharing shared documents
2. Service account edits will appear in version history
3. Consider using a copy for testing

### Company Templates

1. Make a copy of the template
2. Share the copy (not the original)
3. Avoid modifying shared templates

## Troubleshooting

### "Spreadsheet not found" Error

1. Verify the URL is correct
2. Check that you've shared the document with the correct email
3. Make sure you copied the full service account email (including the domain)

### "Permission denied" Error

1. Check the permission level (Viewer won't allow writes)
2. Verify the document is shared with the correct service account
3. Try removing and re-adding sharing

### Can't Find Service Account Email

1. Go to [extrasuite.think41.com](https://extrasuite.think41.com)
2. Sign in (you may have been logged out)
3. The email is displayed in Step 2

### Sharing Not Taking Effect

Google's sharing permissions are usually instant, but occasionally:

1. Wait a few minutes
2. Try removing and re-adding the share
3. Check if the document has sharing restrictions

## Security Considerations

### Version History

All changes made by your AI agent appear in Google's version history:

1. Open the spreadsheet
2. File > Version history > See version history
3. Look for edits by your service account email

### Audit Trail

Every action is logged under your service account identity, making it easy to:

- Track what changes were made
- Revert unwanted changes
- Review agent activity

### Restricting Access

See [Revoking Access](revoking-access.md) for how to remove access when needed.

---

**Next**: Learn how to [revoke access](revoking-access.md) when you no longer need it.
