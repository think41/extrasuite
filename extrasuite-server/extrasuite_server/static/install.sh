#!/bin/bash
set -e
echo "Installing ExtraSuite skills..."
curl -fsSL '__DOWNLOAD_URL__' -o /tmp/es.zip
unzip -oq /tmp/es.zip -d /tmp/es
mkdir -p ~/.claude/skills ~/.codex/skills
for skill in /tmp/es/*/; do
    name=$(basename "$skill")
    cp -R "$skill" ~/.claude/skills/
    cp -R "$skill" ~/.codex/skills/
    echo "  Installed: $name"
done
rm -rf /tmp/es /tmp/es.zip
echo "Done! Skills installed to ~/.claude/skills and ~/.codex/skills"
