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
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\installer_output
OutputBaseFilename=AnimeLoRALibrarySetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
; Intentionally no UninstallDelete entries:
; config, downloads, and logs are preserved when the application is uninstalled.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\AnimeLoRALibrary\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "MigrateData.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "powershell.exe"; Parameters: "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{tmp}\MigrateData.ps1"" ""{app}"" ""{code:GetSourceRoot}"""; Flags: runhidden waituntilterminated; StatusMsg: "Migrating your existing library and settings..."

[Code]
var
  PreviousInstallPage: TInputDirWizardPage;

procedure InitializeWizard();
begin
  PreviousInstallPage := CreateInputDirPage(
    wpSelectDir,
    'Previous installation',
    'Do you have an existing Anime LoRA Library?',
    'Select the folder containing your previous installation. ' +
    'Leave this field empty if this is a fresh installation and you do not need to migrate data.',
    False,
    ''
  );

  PreviousInstallPage.Add('Previous installation folder:');

  if DirExists('C:\CivitaiDownloader') then
    PreviousInstallPage.Values[0] := 'C:\CivitaiDownloader'
  else
    PreviousInstallPage.Values[0] := '';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  SourceRoot: String;
begin
  Result := True;

  if CurPageID = PreviousInstallPage.ID then
  begin
    SourceRoot := Trim(PreviousInstallPage.Values[0]);

    if (SourceRoot <> '') and (not DirExists(SourceRoot)) then
    begin
      MsgBox(
        'The selected previous installation folder does not exist. ' +
        'Please select a valid folder or leave the field empty to skip migration.',
        mbError,
        MB_OK
      );
      Result := False;
    end;
  end;
end;

function GetSourceRoot(Param: String): String;
begin
  Result := Trim(PreviousInstallPage.Values[0]);
end;
