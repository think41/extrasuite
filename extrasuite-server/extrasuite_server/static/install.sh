#!/bin/bash
set -e
echo "Installing ExtraSuite skills..."
curl -fsSL '__DOWNLOAD_URL__' -o /tmp/es.zip
unzip -oq /tmp/es.zip -d /tmp/es
mkdir -p ~/.claude/skills ~/.codex/skills ~/.gemini/skills ~/.config/extrasuite
cp -R /tmp/es/* ~/.claude/skills/
cp -R /tmp/es/* ~/.codex/skills/
cp -R /tmp/es/* ~/.gemini/skills/
echo '{"EXTRASUITE_SERVER_URL": "__SERVER_URL__"}' > ~/.config/extrasuite/gateway.json
chmod 600 ~/.config/extrasuite/gateway.json
rm -rf /tmp/es /tmp/es.zip
# Cleanup old gsheets skill (renamed to gsheetx)
rm -rf ~/.claude/skills/gsheets ~/.codex/skills/gsheets ~/.gemini/skills/gsheets 2>/dev/null || true
echo "Done!"
