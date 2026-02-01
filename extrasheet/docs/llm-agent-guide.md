# LLM Agent Guide

This guide has been reorganized for progressive disclosure. See the [agent-guide/](agent-guide/) directory:

- **[README.md](agent-guide/README.md)** - Start here. Workflow, directory structure, quick reference
- **[formatting.md](agent-guide/formatting.md)** - Colors, fonts, conditional formatting, merges
- **[formulas.md](agent-guide/formulas.md)** - Formula syntax, ranges, compression
- **[features.md](agent-guide/features.md)** - Charts, pivot tables, filters, data validation
- **[structural-changes.md](agent-guide/structural-changes.md)** - Insert/delete rows/columns, batchUpdate workflow
- **[batchupdate-reference.md](agent-guide/batchupdate-reference.md)** - All batchUpdate request types

## Quick Start

```bash
extrasheet pull <url>      # Download spreadsheet
# ... edit files ...
extrasheet diff <folder>   # Preview changes
extrasheet push <folder>   # Apply changes
```

**Key rule:** Always re-pull after push before making more changes.

For full details, see [agent-guide/README.md](agent-guide/README.md).
