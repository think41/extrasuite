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
# Cleanup old skill names (gsheets -> gsheetx -> extrasheet -> extrasuite)
rm -rf ~/.claude/skills/gsheets ~/.codex/skills/gsheets ~/.gemini/skills/gsheets 2>/dev/null || true
rm -rf ~/.claude/skills/gsheetx ~/.codex/skills/gsheetx ~/.gemini/skills/gsheetx 2>/dev/null || true
rm -rf ~/.claude/skills/extrasheet ~/.codex/skills/extrasheet ~/.gemini/skills/extrasheet 2>/dev/null || true
rm -rf ~/.claude/skills/extraslide ~/.codex/skills/extraslide ~/.gemini/skills/extraslide 2>/dev/null || true
rm -rf ~/.claude/skills/extradoc ~/.codex/skills/extradoc ~/.gemini/skills/extradoc 2>/dev/null || true
rm -rf ~/.claude/skills/extraform ~/.codex/skills/extraform ~/.gemini/skills/extraform 2>/dev/null || true
echo "Done!"
