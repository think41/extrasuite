#!/bin/bash
set -e
echo "Installing ExtraSuite skills..."
curl -fsSL '__DOWNLOAD_URL__' -o /tmp/es.zip
unzip -oq /tmp/es.zip -d /tmp/es
mkdir -p ~/.claude/skills ~/.codex/skills ~/.gemini/skills
cp -R /tmp/es/* ~/.claude/skills/
cp -R /tmp/es/* ~/.codex/skills/
cp -R /tmp/es/* ~/.gemini/skills/
rm -rf /tmp/es /tmp/es.zip
echo "Done!"
