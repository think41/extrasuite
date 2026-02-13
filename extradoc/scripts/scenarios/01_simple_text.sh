#!/bin/bash
# Scenario 1: Simple Text Operations
# Tests: insertText, deleteContentRange, updateTextStyle

set -e

DOC_URL="${1:-}"

if [ -z "$DOC_URL" ]; then
  echo "Usage: $0 <google_doc_url>"
  echo ""
  echo "Setup: Create a Google Doc with the text 'Hello World'"
  echo "This scenario will:"
  echo "  1. Insert text after 'Hello'"
  echo "  2. Make 'World' bold"
  exit 1
fi

cd "$(dirname "$0")/../.."

echo "========================================="
echo "Scenario 1: Simple Text Operations"
echo "========================================="
echo ""

# Run the recording script
uv run python scripts/record_scenario.py \
  "$DOC_URL" \
  "Insert the text ' Beautiful' after the word 'Hello', and make the word 'World' bold" \
  --output-dir "./scenario_output/01_simple_text" \
  --mismatch-dir "./mismatch_logs/01_simple_text"

echo ""
echo "✅ Scenario 1 complete!"
