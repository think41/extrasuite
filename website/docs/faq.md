# Frequently Asked Questions

Everything you need to know about using ExtraSuite.

---

## Getting Started

??? question "What is ExtraSuite?"
    ExtraSuite lets AI assistants like Claude Code and Codex declaratively edit your Google Workspace files - Sheets, Docs, Slides, and Forms. Instead of generating code or making API calls, agents pull a file into a compact local representation, edit it, and push changes back. ExtraSuite figures out the minimal API calls to sync everything - like Terraform for Google Workspace.

??? question "How do I get started?"
    Three simple steps:

    1. **Install the skill** - Run the install command from the homepage in your terminal
    2. **Share your document** - Share your Google file with your service account email
    3. **Ask your AI** - Ask Claude Code or Codex to read or modify your document

    See the [Getting Started Guide](getting-started/overview.md) for detailed instructions.

??? question "Which AI assistants are supported?"
    ExtraSuite currently supports:

    - **Claude Code** - Anthropic's coding assistant
    - **Codex CLI** - OpenAI's coding assistant
    - **Gemini CLI** - Google's coding assistant
    - **Claude Coworks** - Anthropic's collaborative workspace
    - **Cursor** - AI-powered code editor

    See [Installation Guides](getting-started/installation/index.md) for platform-specific instructions.

??? question "Which Google Workspace file types are supported?"
    ExtraSuite supports:

    - **Google Sheets** - via `extrasheet` (TSV + JSON representation)
    - **Google Docs** - via `extradoc` (structured document format)
    - **Google Slides** - via `extraslide` (SML/XML format)
    - **Google Forms** - via `extraform` (JSON-based form structure)
    - **Google Apps Script** - upcoming (bound scripts support)

    All file types follow the same pull-edit-diff-push workflow. See [Skills Overview](skills/index.md) for details.

??? question "Do I need to install anything?"
    Yes, a one-time setup. Run the install command from the homepage in your terminal. This adds the ExtraSuite skills to your AI assistant. The installation takes a few seconds.

---

## How It Works

??? question "What does 'declarative editing' mean?"
    Instead of writing code to call Google's API directly, agents edit local file representations. For example, to modify a spreadsheet, the agent edits a TSV file. To update a slide, it edits an XML file. ExtraSuite then computes the minimal API `batchUpdate` to sync the changes back to Google - similar to how Terraform works for infrastructure.

    This is simpler, safer, and more token-efficient than having agents generate imperative API calls.

??? question "What is the pull-edit-diff-push workflow?"
    Every file type follows the same four-step workflow:

    1. **Pull** - Download the Google file into a compact local folder
    2. **Edit** - Agent modifies the local files (TSV, XML, JSON)
    3. **Diff** - Preview what API calls would be made (dry run)
    4. **Push** - Apply the changes to the Google file

    This is consistent across Sheets, Docs, Slides, and Forms.

---

## Security & Privacy

??? question "Can the AI access all my documents?"
    **No.** The AI can only access documents you explicitly share with your service account email. If you don't share a document, the AI cannot see it. This uses standard Google Drive sharing - you're in complete control.

    Learn more in our [Security documentation](security.md).

??? question "Can I revoke access to a document?"
    Yes, instantly. Just remove your service account from the document's sharing settings in Google Drive, the same way you'd remove any other collaborator. Access is revoked immediately.

    See [Revoking Access](user-guide/revoking-access.md) for detailed instructions.

??? question "What if the AI makes a mistake?"
    All changes appear in Google's version history under your agent's name. You can review exactly what changed and use Google's built-in "See version history" feature to undo any changes. Nothing is permanent.

??? question "Is the declarative approach more secure than code generation?"
    Yes. With ExtraSuite, the agent edits local files instead of generating and executing code. This means:

    - No arbitrary code execution
    - No network calls beyond Google Workspace APIs (which can be whitelisted)
    - All changes go through ExtraSuite's diff engine, which computes the minimal `batchUpdate`
    - Changes are attributable and auditable in Google Drive version history

??? question "How long do access tokens last?"
    Access tokens expire after **1 hour**. After that, the skill will automatically prompt you to re-authenticate if needed. No long-lived credentials are stored or distributed.

??? question "Is my data stored on ExtraSuite servers?"
    ExtraSuite stores minimal data:

    - Your email address (for authentication)
    - The mapping between your email and service account

    ExtraSuite does **not** store:

    - Your document contents
    - Access tokens (generated on-demand)
    - Any data from your Google Workspace

---

## Usage

??? question "What can I use this for?"
    Here are some examples across file types:

    **Sheets:**

    - Generate reports from your data
    - Clean up and format messy spreadsheet data
    - Create charts and summaries from raw numbers
    - Automate repetitive spreadsheet tasks

    **Docs:**

    - Draft and edit documents
    - Apply formatting and structure
    - Insert and modify content programmatically

    **Slides:**

    - Build presentations from data
    - Update text, shapes, and layouts
    - Batch-edit slides across a deck

    **Forms:**

    - Create surveys and questionnaires
    - Modify question types and options
    - Update form structure programmatically

    See [Prompting Guide](user-guide/prompting.md) for more examples.

??? question "What's a 'service account email'?"
    It's a special email address that represents your AI assistant. Think of it like a dedicated robot helper that only works for you. When you share a document with this email, you're granting access specifically to your AI assistant.

    Find your service account email on the [ExtraSuite homepage](https://extrasuite.think41.com) after signing in.

??? question "How do I share a document?"
    1. Open your Google Sheet, Doc, Slide, or Form
    2. Click **Share** (top right)
    3. Paste your service account email
    4. Choose permission level (Viewer, Commenter, or Editor)
    5. Click **Send**

    See [Sharing Documents](user-guide/sharing.md) for detailed instructions.

---

## Technical

??? question "What operating systems are supported?"
    - **macOS** - Full support
    - **Linux** - Full support
    - **Windows** - Supported via PowerShell or WSL

    See [Installation Guides](getting-started/installation/index.md) for platform-specific instructions.

??? question "What Python version is required?"
    Python 3.10 or higher is required. The skill creates its own virtual environment, so it won't interfere with your system Python.

??? question "How do I update the skill?"
    Re-run the install command from the ExtraSuite homepage. This downloads the latest version of all skills.

??? question "How do I uninstall?"
    Remove the skill directories:

    ```bash
    rm -rf ~/.claude/skills/gsheetx   # Google Sheets
    rm -rf ~/.claude/skills/extraslide # Google Slides
    # etc.
    ```

??? question "What about Google Apps Script?"
    Apps Script support (starting with bound scripts) is on our roadmap. This will enable agents to manage scripts attached to Sheets, Docs, Slides, and Forms, following the same declarative pull-edit-push workflow.

---

## Troubleshooting

??? question "The install command isn't working"
    1. Make sure you're using the correct command for your OS
    2. The token in the URL expires after 5 minutes - refresh the page for a new one
    3. Check that your terminal has internet access

??? question "I get a 'not found' error"
    1. Verify the URL is correct
    2. Check that you've shared the document with your service account email
    3. Make sure you copied the full service account email (including the domain)

??? question "I get 'Permission denied' error"
    1. Check the permission level (Viewer won't allow writes)
    2. Verify the document is shared with the correct service account
    3. Try removing and re-adding sharing

??? question "Authentication keeps failing"
    1. Clear your browser cookies for extrasuite.think41.com
    2. Re-authenticate through the ExtraSuite homepage
    3. Clear cached tokens:
       ```bash
       rm -f ~/.config/extrasuite/token.json
       ```

??? question "The AI doesn't recognize the skill"
    1. Verify the skill is installed:
       ```bash
       ls ~/.claude/skills/
       ```
    2. Try explicitly mentioning ExtraSuite:
       ```
       Using ExtraSuite, read the data from...
       ```

---

## Support

??? question "I need help. Who do I contact?"
    - **Documentation issues**: Check this FAQ and our [User Guide](user-guide/index.md)
    - **Technical problems**: Contact your IT administrator
    - **Bug reports**: Use internal support channels
    - **Feature requests**: Contact the platform team

??? question "Where can I see what features are planned?"
    Check the [Skills Overview](skills/index.md) for current status and planned features. Google Apps Script support is next on the roadmap.
