# Builds build\LocalConverter-Setup.exe and build\LocalConverter-Portable.exe.
# Needs Python 3.10+ and Inno Setup 6 (installed through Chocolatey if missing).
param([string]$Version = "1.0.0")
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Build = Join-Path $Root "build"
$Tools = Join-Path $Build "tools"
$Version = $Version.TrimStart("v")

Remove-Item $Build -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Tools | Out-Null

# yt-dlp and a shared ffmpeg build (ffmpeg.exe and ffprobe.exe share one set of DLLs).
Invoke-WebRequest "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile "$Tools\yt-dlp.exe"
$Zip = Join-Path $Build "ffmpeg.zip"
Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip" -OutFile $Zip
Expand-Archive $Zip -DestinationPath "$Build\ffmpeg"
$FfmpegBin = (Get-ChildItem "$Build\ffmpeg" -Recurse -Filter ffmpeg.exe | Select-Object -First 1).DirectoryName
Copy-Item "$FfmpegBin\ffmpeg.exe", "$FfmpegBin\ffprobe.exe", "$FfmpegBin\*.dll" $Tools

python -m pip install --upgrade pyinstaller
$Common = @("--noconfirm", "--console", "--icon", "$PSScriptRoot\icon.ico",
            "--add-data", "$Root\index.html;.", "--paths", $Root,
            "--distpath", "$Build\dist", "--workpath", "$Build\work", "--specpath", $Build)

# Installer payload: a folder app, with the tools beside it so yt-dlp can update itself.
python -m PyInstaller @Common --name LocalConverter "$PSScriptRoot\launcher.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Copy-Item $Tools "$Build\dist\LocalConverter\bin" -Recurse

# Portable: one exe with the tools packed inside.
python -m PyInstaller @Common --onefile --name LocalConverter-Portable --add-binary "$Tools\*;bin" "$PSScriptRoot\launcher.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Move-Item "$Build\dist\LocalConverter-Portable.exe" $Build

$Iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $Iscc) { $Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $Iscc)) {
    choco install innosetup -y --no-progress
    $Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
}
& $Iscc "/DAppVersion=$Version" "$PSScriptRoot\installer.iss"
if ($LASTEXITCODE) { throw "Inno Setup failed" }

Get-ChildItem "$Build\LocalConverter-*.exe" | Format-Table Name, Length
