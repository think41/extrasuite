$ErrorActionPreference = "Stop"
Write-Host "Installing ExtraSuite skills..."
$tmp = "$env:TEMP\extrasuite-install"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Invoke-WebRequest -Uri '__DOWNLOAD_URL__' -OutFile "$tmp\skills.zip"
Expand-Archive -Path "$tmp\skills.zip" -DestinationPath "$tmp\extracted" -Force
$targetDirs = @("$env:USERPROFILE\.claude\skills", "$env:USERPROFILE\.codex\skills")
foreach ($dir in $targetDirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
Get-ChildItem -Path "$tmp\extracted" -Directory | ForEach-Object {
    $skillName = $_.Name
    foreach ($dir in $targetDirs) {
        Copy-Item -Path $_.FullName -Destination $dir -Recurse -Force
    }
    Write-Host "  Installed: $skillName"
}
Remove-Item -Path $tmp -Recurse -Force
Write-Host "Done! Skills installed."
