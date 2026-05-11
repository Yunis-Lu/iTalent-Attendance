$ErrorActionPreference = "Stop"

$argsList = @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--onefile",
  "--paths", "iTalent-Attendance",
  "--icon", "assets\italent_icon_true_transparent.ico",
  "--add-data", "assets\italent_icon_true_transparent.ico;assets",
  "--add-data", "assets\italent_icon_true_transparent.png;assets",
  "--name", "iTalent-Attendance",
  "iTalent-Attendance\tk_main.py"
)

python -m PyInstaller @argsList
