#!/bin/bash
# Scenario 4: Table Operations
# Tests: insertTable, insertText in table cells

set -e

DOC_URL="${1:-}"

if [ -z "$DOC_URL" ]; then
  echo "Usage: $0 <google_doc_url>"
  echo ""
  echo "Setup: Create a Google Doc with text 'Quarterly Report'"
  echo "This scenario will insert a table below it"
  exit 1
fi

cd "$(dirname "$0")/../.."

echo "========================================="
echo "Scenario 4: Table Operations"
echo "========================================="
echo ""

uv run python scripts/record_scenario.py \
  "$DOC_URL" \
  "Insert a 3x3 table after the first paragraph. Fill the first row with: Product, Q1, Q2" \
  --output-dir "./scenario_output/04_tables" \
  --mismatch-dir "./mismatch_logs/04_tables"

echo ""
echo "✅ Scenario 4 complete!"
