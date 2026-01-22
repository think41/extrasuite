$ErrorActionPreference = "Stop"
Write-Host "Installing ExtraSuite skills..."
$tmp = "$env:TEMP\extrasuite-install"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Invoke-WebRequest -Uri '__DOWNLOAD_URL__' -OutFile "$tmp\skills.zip"
Expand-Archive -Path "$tmp\skills.zip" -DestinationPath "$tmp\extracted" -Force
$dirs = @("$env:USERPROFILE\.claude\skills", "$env:USERPROFILE\.codex\skills", "$env:USERPROFILE\.gemini\skills")
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Copy-Item -Path "$tmp\extracted\*" -Destination $dir -Recurse -Force
}
$configDir = "$env:USERPROFILE\.config\extrasuite"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
'{"EXTRASUITE_SERVER_URL": "__SERVER_URL__"}' | Out-File -FilePath "$configDir\gateway.json" -Encoding UTF8
Remove-Item -Path $tmp -Recurse -Force
# Cleanup old gsheets skill (renamed to gsheetx)
foreach ($dir in $dirs) {
    $oldSkill = Join-Path $dir "gsheets"
    if (Test-Path $oldSkill) { Remove-Item -Path $oldSkill -Recurse -Force -ErrorAction SilentlyContinue }
}
Write-Host "Done!"
