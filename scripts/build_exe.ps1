$ErrorActionPreference = "Stop"

$appVersion = "v0.2"
$appName = "iTalent-Attendance.$appVersion"

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

python -m PyInstaller @argsList
