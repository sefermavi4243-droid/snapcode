; Inno Setup script. Build with: ISCC.exe /DAppVersion=1.2.0 packaging\installer.iss
; Per-user install: no admin prompt, no UAC.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Pluck"
#define AppExe "Pluck.exe"
; Up to 1.4 the app was SnapCode, in 1.5 CodeLift; the same AppId upgrades it in place.
#define LegacyName "SnapCode"
#define LegacyName2 "CodeLift"

[Setup]
AppId={{6F1C5B8E-2D4A-4F7B-9C3E-8A1D2B7E4C90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Sefer Mavi
AppPublisherURL=https://github.com/sefermavi4243-droid/snapcode
AppSupportURL=https://github.com/sefermavi4243-droid/snapcode/issues
AppUpdatesURL=https://github.com/sefermavi4243-droid/snapcode/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\build\installer
OutputBaseFilename=Pluck-Setup-{#AppVersion}
SetupIconFile=snapcode.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no
VersionInfoVersion={#AppVersion}

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
turkish.AutoStart=Windows açıldığında Pluck'i başlat
english.AutoStart=Start Pluck when Windows starts
turkish.Launch=Pluck'i şimdi başlat
english.Launch=Launch Pluck now

[Tasks]
Name: "autostart"; Description: "{cm:AutoStart}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\build\dist\Pluck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[InstallDelete]
; Leftovers of the SnapCode name.
Type: files; Name: "{app}\{#LegacyName}.exe"
Type: files; Name: "{autoprograms}\{#LegacyName}.lnk"
Type: files; Name: "{autodesktop}\{#LegacyName}.lnk"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "{#LegacyName}"; Flags: deletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// A tray app has no window to close politely, so stop it before files are
// replaced (upgrade) or removed (uninstall). Settings and history live in
// %APPDATA%\Pluck (moved from %APPDATA%\CodeLift or SnapCode on first start) and are kept.
procedure StopApp();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe} /IM {#LegacyName}.exe /IM {#LegacyName2}.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(300);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopApp();
  Result := True;
end;
