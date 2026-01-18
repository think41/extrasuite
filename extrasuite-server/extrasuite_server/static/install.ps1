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
Remove-Item -Path $tmp -Recurse -Force
Write-Host "Done!"
