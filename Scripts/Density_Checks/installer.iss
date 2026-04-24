; -----------------------------
; Last Return Density Checker - Inno Setup Script v1.5.0
; -----------------------------

#define MyAppName "Last Return Density Checker"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "GeoBC - Nikolay Senilov & Spencer Floyd"
#define MyAppExeName "LastReturnDensityChecker.exe"

; Folder that contains the EXE (from PyInstaller output)
; Relative to this .iss file — produced by running build.bat
#define MyAppSourceDir "dist\LastReturnDensityChecker"

; Generate a stable GUID for upgrades (Tools -> Generate GUID in Inno Setup)
; IMPORTANT: Replace this with your own GUID or use the one from your v1.0
#define MyAppId "{{5E9F8A42-7D3C-4B1F-9A2E-8C6D4F7B3E1A}}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName} {#MyAppVersion}

; Install to user's local appdata (no admin required)
DefaultDirName={localappdata}\{#MyAppPublisher}\LastReturnDensityChecker
PrivilegesRequired=lowest

DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output settings
OutputDir=installer_output
OutputBaseFilename=LastReturnDensityChecker_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=2

; Architecture settings
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; Icon settings (MUST exist or compile will fail)
SetupIconFile={#MyAppSourceDir}\_internal\assets\LastReturnDensityChecker_Icon.ico
UninstallDisplayIcon={app}\_internal\assets\LastReturnDensityChecker_Icon.ico

; Modern wizard style
WizardStyle=modern
WizardSizePercent=100

; Version info
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCopyright=Copyright (C) 2025 {#MyAppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Include ALL files from PyInstaller output directory
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start menu shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "LiDAR Density Analysis Tool"

; Desktop shortcut (optional)
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "LiDAR Density Analysis Tool"

[Run]
; Option to launch after installation
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up user data on uninstall (optional - remove if you want to keep user settings)
Type: filesandordirs; Name: "{userappdata}\GeoBC\LastReturnDensityChecker"

[Code]
// Check if upgrading from previous version
function InitializeSetup(): Boolean;
var
  OldVersion: String;
begin
  Result := True;

  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1', 'DisplayVersion', OldVersion) then
  begin
    if MsgBox('Version ' + OldVersion + ' is already installed. Do you want to upgrade to version {#MyAppVersion}?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
