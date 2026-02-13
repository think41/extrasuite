#!/bin/bash
# Scenario 2: Heading Formatting
# Tests: updateParagraphStyle with headingId

set -e

DOC_URL="${1:-}"

if [ -z "$DOC_URL" ]; then
  echo "Usage: $0 <google_doc_url>"
  echo ""
  echo "Setup: Create a Google Doc with plain text 'Chapter One' on the first line"
  echo "This scenario will convert it to a Heading 1"
  exit 1
fi

cd "$(dirname "$0")/../.."

echo "========================================="
echo "Scenario 2: Heading Formatting"
echo "========================================="
echo ""

uv run python scripts/record_scenario.py \
  "$DOC_URL" \
  "Convert the first paragraph to a Heading 1 style" \
  --output-dir "./scenario_output/02_headings" \
  --mismatch-dir "./mismatch_logs/02_headings"

echo ""
echo "✅ Scenario 2 complete!"
