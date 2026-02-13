#!/bin/bash
# Scenario 3: Bulleted Lists
# Tests: createParagraphBullets

set -e

DOC_URL="${1:-}"

if [ -z "$DOC_URL" ]; then
  echo "Usage: $0 <google_doc_url>"
  echo ""
  echo "Setup: Create a Google Doc with 3 separate paragraphs:"
  echo "  Item One"
  echo "  Item Two"
  echo "  Item Three"
  echo ""
  echo "This scenario will convert them to a bulleted list"
  exit 1
fi

cd "$(dirname "$0")/../.."

echo "========================================="
echo "Scenario 3: Bulleted Lists"
echo "========================================="
echo ""

uv run python scripts/record_scenario.py \
  "$DOC_URL" \
  "Convert all paragraphs in the document to a bulleted list" \
  --output-dir "./scenario_output/03_lists" \
  --mismatch-dir "./mismatch_logs/03_lists"

echo ""
echo "✅ Scenario 3 complete!"
