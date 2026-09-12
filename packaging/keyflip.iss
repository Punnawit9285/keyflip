; Inno Setup script for keyflip.  Built in CI:  iscc packaging\keyflip.iss
;
; Installs per-user, on purpose.  keyflip needs no administrator rights to do
; its job, so asking for them would mean a UAC prompt and an elevation warning
; on every install - for a menu-bar utility that only ever talks to the
; clipboard.  Per-user also means uninstalling really does remove everything.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "keyflip"
#define MyAppExe  "keyflip.exe"
#define RunKey    "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={{7C4E1D2A-9B3F-4A16-8E55-6D0F2A1B8C43}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=keyflip
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=keyflip-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
LicenseFile=..\LICENSE

[Files]
Source: "..\dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md";        DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#MyAppName}";          Filename: "{app}\{#MyAppExe}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Tasks]
Name: "startup"; Description: "Start {#MyAppName} when I sign in"; GroupDescription: "Startup:"

; The same registry value the app's own "Start at login" menu item writes, so
; the installer checkbox and the menu tick can never disagree with each other.
[Registry]
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "keyflip"; \
    ValueData: """{app}\{#MyAppExe}"" run"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Start {#MyAppName} now"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; The tray app holds no lock, but leaving it running after an uninstall would
; keep a deleted exe alive in memory until the next reboot.
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#MyAppExe}"; Flags: runhidden; RunOnceId: "StopKeyflip"
