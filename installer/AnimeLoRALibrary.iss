#define MyAppName "Anime LoRA Library"
#define MyAppVersion "1.0.0"
#define MyAppExeName "AnimeLoRALibrary.exe"

[Setup]
AppId={{B1A3C8D2-4F67-49A1-9E35-7D2C8B6F1042}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Anime LoRA Library
DefaultDirName={localappdata}\Programs\Anime LoRA Library
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\installer_output
OutputBaseFilename=AnimeLoRALibrarySetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\AnimeLoRALibrary\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "MigrateData.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "powershell.exe"; Parameters: "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{tmp}\MigrateData.ps1"" ""{app}"""; Flags: runhidden waituntilterminated; StatusMsg: "Migrating your existing library and settings..."

; Intentionally no UninstallDelete entries:
; config, downloads, and logs are preserved when the application is uninstalled.
