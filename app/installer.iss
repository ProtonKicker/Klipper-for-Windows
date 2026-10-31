; Klipper for Windows - self-contained installer
; Lays down the GUI + bundled runtime (Python, patched Klipper/Moonraker,
; Mainsail/Fluidd), creates shortcuts and a PATH shim for the CLI.

#define AppName "Klipper for Windows"
#define AppExeName "Klipper for Windows"
#define AppVersion "0.1.1"

[Setup]
AppId={{8F4A9C21-5D3E-4B7A-9C1F-2E6D8A4B7C93}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ProtonKicker
DefaultDirName={localappdata}\KlipperForWindows
DisableDirPage=no
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=KlipperForWindows-{#AppVersion}-installer
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExeName}.exe
SetupIconFile=KlipperForWindows\Assets\appicon.ico
WizardStyle=modern
CloseApplications=yes

[Files]
Source: "..\dist\portable\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{userdocs}\Klipper for Windows"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "pathshim"; Description: "Add klipperforwindows CLI to &PATH"; GroupDescription: "Integration:"

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}\bin"; Tasks: pathshim; \
    Check: NeedsPathShim

[Run]
Filename: "{app}\{#AppExeName}.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; data folder in Documents is intentionally preserved

[Code]
function NeedsPathShim(): Boolean;
var
  UserPath: String;
begin
  Result := True;
  if RegQueryStringValue(HKCU, 'Environment', 'Path', UserPath) then
    Result := Pos(Uppercase(ExpandConstant('{app}\bin')), Uppercase(UserPath)) = 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ShimDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    // CLI shim: klipperforwindows.cmd -> bundled python -m klipperforwindows
    ShimDir := ExpandConstant('{app}\bin');
    ForceDirectories(ShimDir);
    SaveStringToFile(ShimDir + '\klipperforwindows.cmd',
      '@echo off' + #13#10 +
      '"%~dp0..\runtime\python\python.exe" -m klipperforwindows %*' + #13#10,
      False);
  end;
end;
