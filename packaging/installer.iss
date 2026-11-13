#define MyAppName "ai-screenshot"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3C1B42-5C7E-4A19-9E31-6D2A0B7C4E55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=ai-screenshot
DefaultDirName={localappdata}\ai-screenshot
DefaultGroupName=ai-screenshot
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ai-screenshot-{#MyAppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}

[Files]
Source: "..\dist\ai-screenshot.exe"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut (Ctrl+Alt+Q)"; GroupDescription: "Shortcuts:"

[Icons]
Name: "{group}\Capture and answer"; Filename: "{app}\ai-screenshot.exe"; Hotkey: ctrl+alt+q
Name: "{group}\Settings"; Filename: "{app}\ai-screenshot.exe"; Parameters: "--settings"; Hotkey: ctrl+alt+s
Name: "{group}\Uninstall ai-screenshot"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ai-screenshot"; Filename: "{app}\ai-screenshot.exe"; Hotkey: ctrl+alt+q; Tasks: desktopicon

[Run]
Filename: "{app}\ai-screenshot.exe"; Parameters: "--settings"; Description: "Open settings now"; Flags: postinstall nowait skipifsilent
