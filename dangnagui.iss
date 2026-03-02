#define MyAppName "dangnagui"
#define MyAppDisplayName "dangnagui"
#define MyAppVersion "1.2.2"
#define MyAppPublisher "Chally"
#define MyAppURL "mailto:challychoi@me.com"
#define MyAppExeName "dangnagui.exe"

[Setup]
AppId={{A7B8C9D0-1234-5678-ABCD-DANGNAGUI09}}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppDisplayName}
OutputDir=Output
OutputBaseFilename=dangnagui-setup-v1.2.2
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppDisplayName}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\dangnagui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "readme.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Readme"; Filename: "{app}\readme.txt"
Name: "{group}\{cm:UninstallProgram,{#MyAppDisplayName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch dangnagui"; Flags: nowait postinstall skipifsilent

[Dirs]
Name: "{app}\IMoutput"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify

[UninstallDelete]
Type: filesandordirs; Name: "{app}\IMoutput"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\app_settings.json"
Type: files; Name: "{app}\app_settings.json.bak"
Type: files; Name: "{app}\.instance.lock"
