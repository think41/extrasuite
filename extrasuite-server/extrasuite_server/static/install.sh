#!/bin/bash
set -e
echo "Installing ExtraSuite skills..."
curl -fsSL '__DOWNLOAD_URL__' -o /tmp/es.zip
unzip -oq /tmp/es.zip -d /tmp/es
mkdir -p ~/.claude/skills ~/.codex/skills
cp -R /tmp/es/gsheets ~/.claude/skills/
cp -R /tmp/es/gsheets ~/.codex/skills/
rm -rf /tmp/es /tmp/es.zip
echo "Done! Skills installed to ~/.claude/skills and ~/.codex/skills"
