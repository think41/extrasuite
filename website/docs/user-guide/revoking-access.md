# Revoking Access

Learn how to remove your AI agent's access to documents and manage permissions.

## Overview

Revoking access in ExtraSuite is straightforward because it uses standard Google Drive sharing. When you remove your service account from a document's sharing settings, access is revoked **immediately**.

## Revoking Access to a Single Document

### Via Google Sheets

1. Open the Google Sheet
2. Click **Share** (top right)
3. Find your service account email in the list
4. Click the dropdown next to their name
5. Select **Remove**
6. Click **Save**

### Via Google Drive

1. Open [Google Drive](https://drive.google.com)
2. Right-click the file
3. Select **Share** > **Share**
4. Find your service account email
5. Click the dropdown and select **Remove**
6. Click **Save**

## Revoking Access to Multiple Documents

### If Documents Are in a Folder

1. Open [Google Drive](https://drive.google.com)
2. Right-click the shared folder
3. Select **Share** > **Share**
4. Find your service account email
5. Click **Remove**
6. All documents in the folder will lose access

### Finding All Shared Documents

To find all documents shared with your agent:

1. Open [Google Drive](https://drive.google.com)
2. In the search bar, type your service account email
3. This shows all documents shared with that email
4. Remove sharing from each as needed

!!! tip "Search Syntax"
    You can use `to:yourname-domain@project.iam.gserviceaccount.com` in Google Drive search to find shared documents.

## Revoking All Access

If you want to completely remove your AI agent's ability to access any of your documents:

### Step 1: Find All Shared Documents

Search in Google Drive for your service account email to find all shared documents.

### Step 2: Remove from Each Document

Remove the service account from each document's sharing settings.

### Step 3: Check Shared Folders

Also check any folders that might be shared:

1. My Drive > Shared folders
2. Remove service account from any relevant folders

## What Happens After Revoking

When you revoke access:

| Action | Result |
|--------|--------|
| Immediate | Agent loses access to the document |
| API calls | Will fail with "permission denied" |
| Cached data | Agent may remember data from before revocation |
| Version history | Past edits remain in history |

!!! warning "Cached Data"
    Your AI agent may have cached or discussed the data during your conversation. Revoking access prevents future access but doesn't delete conversation history.

## Temporary vs Permanent Access

### Temporary Access Pattern

For one-time tasks:

1. Share document with Editor access
2. Complete the task with your AI agent
3. Immediately revoke access
4. Document is protected going forward

### Permanent Access Pattern

For ongoing workflows:

1. Share document with appropriate permissions
2. Keep access while workflow is active
3. Revoke when project ends or workflow changes

## Verifying Revocation

### Test Access

After revoking, ask your AI agent:

```
Read the data from https://docs.google.com/spreadsheets/d/abc123/edit
```

You should see an error indicating the document is not accessible.

### Use Verification Script

```bash
~/.claude/skills/gsheets/venv/bin/python ~/.claude/skills/gsheets/verify_access.py <spreadsheet-url>
```

This should fail if access was properly revoked.

## Reverting Unwanted Changes

If your AI agent made changes you want to undo:

### Use Version History

1. Open the Google Sheet
2. File > Version history > See version history
3. Find the version before the unwanted changes
4. Click **Restore this version**

### Selective Undo

For specific changes:

1. View version history
2. Click on a previous version
3. Copy the cells you want to restore
4. Go back to current version
5. Paste the old values

## Emergency Access Removal

If you need to immediately stop all access:

### Quick Steps

1. Go to [Google Drive](https://drive.google.com)
2. Search for your service account email
3. Select all matching documents
4. Right-click > Share > Remove service account from all

### Delete Cached Tokens

Remove local token cache:

```bash
rm -f ~/.config/extrasuite/token.json
```

This prevents the skill from using any existing authentication.

## Re-Granting Access

If you revoked access by mistake:

1. Open the document
2. Click **Share**
3. Add your service account email again
4. Set the appropriate permission level

Access is restored immediately.

## Access Audit

### Checking Current Permissions

For any document:

1. Open the document
2. Click **Share**
3. Review the list of people with access

### Finding Unexpected Access

Periodically review:

1. Documents shared with your service account
2. Folders that might grant transitive access
3. Shared drives that include your service account

## Best Practices

### 1. Regular Access Review

Set a reminder to review shared documents monthly:

- Remove access from completed projects
- Verify only necessary documents are shared
- Check folder-level sharing

### 2. Document Access in Notes

Keep a record of what you've shared:

```
Project: Q4 Analysis
Shared: https://docs.google.com/spreadsheets/d/abc123
Permission: Editor
Purpose: Automated report generation
Revoke after: 2024-12-31
```

### 3. Use Time-Limited Access

For sensitive data:

1. Share only when actively working
2. Revoke immediately after completion
3. Don't leave Editor access on important documents

### 4. Prefer Viewer Access

When possible:

1. Start with Viewer access for analysis
2. Grant Editor only when needed
3. Revoke back to Viewer after changes are complete

---

**Related Topics:**

- [Sharing Documents](sharing.md) - How to grant access
- [Security](../security.md) - ExtraSuite's security model
- [FAQ](../faq.md) - Common questions
