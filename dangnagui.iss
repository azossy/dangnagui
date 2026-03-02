#define MyAppName "dangnagui"
#define MyAppDisplayName "당나귀 게시판검색기"
#define MyAppVersion "1.3.1"
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
OutputBaseFilename=dangnagui-setup-v1.3.1
SetupIconFile=dangnagui.ico
UninstallDisplayIcon={app}\dangnagui.ico
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
Source: "dangnagui.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "korean_sites_seed.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\dangnagui.ico"
Name: "{group}\Readme"; Filename: "{app}\readme.txt"
Name: "{group}\{cm:UninstallProgram,{#MyAppDisplayName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\dangnagui.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppDisplayName}"; Flags: nowait postinstall skipifsilent

[Dirs]
Name: "{app}\IMoutput"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify

[UninstallDelete]
Type: filesandordirs; Name: "{app}\IMoutput"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\app_settings.json"
Type: files; Name: "{app}\app_settings.json.bak"
Type: files; Name: "{app}\sites_db.enc"
Type: files; Name: "{app}\sites_db.enc.bak"
Type: files; Name: "{app}\.instance.lock"
