; Inno Setup script for keyflip.  Built in CI:  iscc packaging\keyflip.iss
;
; One click: open it, press Install, and keyflip is running.  Every page that
; asked a question is gone, because none of the questions needed asking -
; there is nowhere better to put it, nothing to choose between, and nothing
; that needs administrator rights.  The Ready page stays, and should: one
; confirmation before software lands on a machine is the right number.
;
; Per-user on purpose.  keyflip needs no administrator rights to do its job,
; so asking for them would mean a UAC prompt on every install - for a tray
; utility that only ever talks to the clipboard.  Per-user also means
; uninstalling really does remove everything.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.1"
#endif

#define MyAppName "keyflip"
#define MyAppExe  "keyflip.exe"
#define RunKey    "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={{7C4E1D2A-9B3F-4A16-8E55-6D0F2A1B8C43}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=keyflip
AppPublisherURL=https://github.com/Punnawit9285/keyflip
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=keyflip-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExe}
; No questions: straight to the Ready page, and gone as soon as it is done.
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableFinishedPage=yes
ShowLanguageDialog=no
; A running copy is stopped in PrepareToInstall below, so the Restart
; Manager's "close these applications?" page never needs to appear.
CloseApplications=no

[Messages]
ReadyLabel1=keyflip is ready to install.
ReadyLabel2b=Click Install. keyflip starts as soon as it is done.

[Files]
Source: "..\dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";        DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE";          DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";           Filename: "{app}\{#MyAppExe}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; The same registry value the app's own "Start at login" menu item writes, so
; the installer and the menu tick can never disagree.  Fresh installs only:
; an upgrade must not switch it back on for someone who unticked it.
[Registry]
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "keyflip"; \
    ValueData: """{app}\{#MyAppExe}"" run"; Flags: uninsdeletevalue; Check: IsFirstInstall

; --welcome raises a notification.  With no finished page the setup window
; just closes, and Windows 11 tucks new tray icons out of sight - without it
; a successful install looks exactly like nothing happening.
[Run]
Filename: "{app}\{#MyAppExe}"; Parameters: "run --welcome"; Flags: nowait

[UninstallRun]
; Leaving it running after an uninstall would keep a deleted exe alive in
; memory, still reading the shortcut, until the next reboot.
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#MyAppExe}"; Flags: runhidden; RunOnceId: "StopKeyflip"

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7C4E1D2A-9B3F-4A16-8E55-6D0F2A1B8C43}_is1';

var
  WasInstalled: Boolean;

function InitializeSetup(): Boolean;
begin
  // Decide once, before anything is written: by the time [Registry] runs,
  // this very install may already have created its own uninstall key.
  WasInstalled := RegKeyExists(HKCU, UninstallKey);
  Result := True;
end;

function IsFirstInstall(): Boolean;
begin
  Result := not WasInstalled;
end;

// The Ready page is the only thing anyone sees, so make it say what matters:
// that keyflip will start at sign-in, and how to use it at all.
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine;
  if IsFirstInstall() then
    Result := Result + 'Starts automatically when you sign in.' + NewLine +
      Space + 'Untick "Start at login" in the tray menu to turn that off.' +
      NewLine + NewLine;
  Result := Result + 'How to use it:' + NewLine +
    Space + 'Select text typed in the wrong keyboard layout,' + NewLine +
    Space + 'then tap the Right Shift key twice.';
end;

// A running keyflip holds its own exe open, and copying over it would stop an
// upgrade on a "file in use" error - the opposite of one click.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im {#MyAppExe}', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);  // let the handle close before the copy starts
  Result := '';
end;
