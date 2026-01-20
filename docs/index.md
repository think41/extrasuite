# ExtraSuite for Google Workspace

<div class="hero" markdown>

**Connect AI agents to your Google Workspace.**
Read, analyze, and edit spreadsheets with natural language.

[Get Started](getting-started/overview.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/think41/extrasuite){ .md-button }

</div>

---

## What is ExtraSuite?

ExtraSuite connects AI coding assistants like **Claude Code**, **Codex CLI**, and **Gemini CLI** to your Google Workspace. Instead of copy-pasting data, you can ask your AI to read, analyze, and edit your spreadsheets directly.

<div class="grid cards" markdown>

-   :material-lock:{ .lg .middle } **You Stay in Control**

    ---

    AI agents can only access documents you explicitly share. Revoke access anytime through standard Google Drive sharing.

-   :material-history:{ .lg .middle } **Full Auditability**

    ---

    All changes appear in Google's version history under the agent's identity. Review and undo any changes instantly.

-   :material-timer-sand:{ .lg .middle } **Short-Lived Tokens**

    ---

    Access tokens expire after 1 hour. No long-lived credentials are stored or distributed.

-   :material-shield-check:{ .lg .middle } **Enterprise Security**

    ---

    Built on Google Cloud IAM with domain restrictions and service account impersonation.

</div>

---

## How It Works

<div class="grid" markdown>

<div markdown>

### Step 0: Install an AI Agent { data-step="0" }

Get [Claude Code](https://claude.ai/code), [Codex CLI](https://openai.com/index/introducing-codex/), or [Gemini CLI](https://ai.google.dev/gemini-api/docs/aistudio-quickstart) on your machine.

</div>

<div markdown>

### Step 1: Install the Skill { data-step="1" }

Run a one-time command to add Google Sheets access to your AI agent.

</div>

<div markdown>

### Step 2: Share Your Document { data-step="2" }

Share your Google Sheet with your service account email (provided after install).

</div>

<div markdown>

### Step 3: Put It to Work { data-step="3" }

Use natural language to work with your spreadsheet. The more context you provide, the better the results.

</div>

</div>

---

## Real Examples

!!! example "Complex Analytics Report"

    > "I am meeting the CEO of [client]. They have been piloting with us and used 75+ interviews across several roles. Through linkedin posts and press releases, I see they are hiring BD managers for RPOs in Middle East, Singapore, and Australia.
    >
    > I need candidate-side metrics: candidates invited, completed interviews, no-shows, and those who engaged 5+ minutes. For dropoffs, analyze if it was bad experience, technical issues, or self-selection.
    >
    > On user-side: when was the interview created, when the first candidate was added, and time from candidate addition to interview completion.
    >
    > Use the r41 sql tool to fetch data. Use the gsheets skill to update the data to https://docs.google.com/spreadsheets/..."

    — *Dr. Swetha Suresh, Co-founder Recruit41*

!!! example "Financial MIS Report"

    > "Help me make a MIS report for Think41 financials. Pull the data from zoho using zoho skill. Update the data in this spreadsheet https://docs.google.com/spreadsheets/..."

    — *Himanshu Varshney, Think41 Technologies*

---

## Supported Skills

| Skill | Status | Description |
|-------|--------|-------------|
| **Google Sheets** | :material-check-circle:{ .text-green } Stable | Read, write, and manipulate spreadsheets |
| **Google Docs** | :material-flask:{ .text-orange } Alpha | Create and edit documents |
| **Google Slides** | :material-flask:{ .text-orange } Alpha | Build presentations |

---

## Quick Links

- [Installation Guides](getting-started/installation/index.md) - Platform-specific setup instructions
- [User Guide](user-guide/index.md) - Learn how to prompt, share, and manage access
- [Security](security.md) - Understand the security model
- [FAQ](faq.md) - Common questions answered

---

<div class="footer-note" markdown>
!!! warning "Internal Use"
    This service is for internal use by employees of think41.com, recruit41.com, and mindlap.dev.
</div>
