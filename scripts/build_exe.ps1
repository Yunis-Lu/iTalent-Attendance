[CmdletBinding()]
param(
  [string]$Version = "v0.2"
)

$ErrorActionPreference = "Stop"

$appVersion = $Version
$appName = "iTalent-Attendance.$appVersion"
$versionFile = Join-Path $PSScriptRoot "..\iTalent-Attendance\version.py"
$originalVersion = Get-Content -Raw -Encoding UTF8 $versionFile
$utf8NoBom = New-Object System.Text.UTF8Encoding $false

$argsList = @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--onefile",
  "--paths", "iTalent-Attendance",
  "--icon", "assets\italent_icon_true_transparent.ico",
  "--add-data", "assets\italent_icon_true_transparent.ico;assets",
  "--add-data", "assets\italent_icon_true_transparent.png;assets",
  "--name", $appName,
  "iTalent-Attendance\tk_main.py"
)

try {
  [System.IO.File]::WriteAllText($versionFile, "APP_VERSION = `"$appVersion`"`r`n", $utf8NoBom)
  python -m PyInstaller @argsList
}
finally {
  [System.IO.File]::WriteAllText($versionFile, $originalVersion, $utf8NoBom)
}
