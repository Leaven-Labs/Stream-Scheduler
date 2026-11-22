; The Windows installer (Inno Setup 6.3 or newer). tools/build.py runs this after PyInstaller:
;   iscc /DAppVersion=0.0.7-alpha /DAppVersionNumber=0.0.7 tools\installer.iss
;   -> dist\Stream-Scheduler-Windows-Setup.exe
;
; It installs for the person who runs it, with no administrator prompt:
;   the program   %LOCALAPPDATA%\Programs\Stream Scheduler   (replaced by every update)
;   the settings  %APPDATA%\Stream Scheduler                  (never touched: they survive updates and removal)
;   the sign-ins  Windows Credential Manager                  (never touched)
; "Start when I sign in" is the same HKCU Run value that the app's own Settings switch writes (autostart.py).

#define AppName "Stream Scheduler"
#define AppExe "Stream Scheduler.exe"
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppVersionNumber
  #define AppVersionNumber "0.0.0"
#endif

[Setup]
; AppId names this program to Windows for updates and removal: never change it.
AppId={{6C1B0C55-9C0D-4E0B-8F5E-5A1D5B6E3F27}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Leaven Labs
AppPublisherURL=https://github.com/Leaven-Labs/Stream-Scheduler
VersionInfoVersion={#AppVersionNumber}
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SourceDir=..
OutputDir=dist
OutputBaseFilename=Stream-Scheduler-Windows-Setup
SetupIconFile=build\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
; The running copy is stopped by StopApp below, which lets it finish properly.
CloseApplications=no

[Tasks]
; Only asked on a first install: an update leaves the choice made in the app's Settings alone.
Name: "autostart"; Description: "Start {#AppName} when I sign in to Windows (hidden in the tray, so streams are scheduled on time)"; Check: not IsUpgrade
Name: "desktopicon"; Description: "Put a shortcut on the desktop"; Flags: unchecked; Check: not IsUpgrade

[InstallDelete]
; The program's own libraries: an update must not keep files of the version before it.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --tray"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
; Off unless ticked: it only opens the explanation (Settings -> Unattended PC); nothing changes before the
; person reads what automatic sign-in does and agrees to it there.
Filename: "{app}\{#AppExe}"; Parameters: "--unattended"; Description: "Set this PC up to run unattended (opens the explanation in {#AppName})"; Flags: nowait postinstall skipifsilent unchecked

[Code]
function IsUpgrade: Boolean;
begin
  Result := RegKeyExists(HKCU, ExpandConstant(
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1'));
end;

{ Stop the copy that is running, so its files can be replaced. First ask it (it finishes what it is doing),
  then end whatever is left, such as an older copy that was started from an unzipped folder. }
procedure StopApp(Dir: String);
var
  Code: Integer;
begin
  if FileExists(Dir + '\{#AppExe}') then
    Exec(Dir + '\{#AppExe}', '--quit', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'),
       '/F /FI "USERNAME eq ' + GetUserNameString + '" /IM "{#AppExe}"', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopApp(ExpandConstant('{app}'));
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    StopApp(ExpandConstant('{app}'));
    RegDeleteValue(HKCU, '{#RunKey}', '{#AppName}');
  end;
end;
