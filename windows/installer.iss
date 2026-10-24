; Inno Setup script. Run windows\build.ps1 first; it builds the files this packages.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8F3C2A51-6B7D-4E0A-9C1F-2D5E7A9B3C40}
AppName=Local Converter
AppVersion={#AppVersion}
AppPublisher=Chaiporn2005
DefaultDirName={localappdata}\Programs\Local Converter
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, and yt-dlp can update itself in place.
PrivilegesRequired=lowest
OutputDir=..\build
OutputBaseFilename=LocalConverter-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\LocalConverter.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\dist\LocalConverter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Local Converter"; Filename: "{app}\LocalConverter.exe"
Name: "{autodesktop}\Local Converter"; Filename: "{app}\LocalConverter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LocalConverter.exe"; Description: "{cm:LaunchProgram,Local Converter}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; yt-dlp's self-update leaves files the installer did not create.
Type: filesandordirs; Name: "{app}\bin"
