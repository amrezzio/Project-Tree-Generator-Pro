[Setup]
AppName=Project Tree Generator Pro
AppVersion=1.0.0
AppPublisher=AmirReza
DefaultDirName={autopf}\Project Tree Generator Pro
DefaultGroupName=Project Tree Generator Pro
UninstallDisplayName=Project Tree Generator Pro
UninstallDisplayIcon={app}\main.exe
PrivilegesRequired=admin
OutputDir=.\Release
OutputBaseFilename=ProjectTreeGeneratorPro_Setup
SetupIconFile=src\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dynamic
WizardResizable=yes

[Files]
Source: "dist\main\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "src\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "version.txt"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}"; Permissions: users-modify

[Icons]
Name: "{group}\Project Tree Generator Pro"; Filename: "{app}\main.exe"
Name: "{group}\Uninstall Project Tree Generator Pro"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Project Tree Generator Pro"; Filename: "{app}\main.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
; Removed 'skipifsilent' so the app launches automatically after a silent update
Filename: "{app}\main.exe"; Description: "Launch Project Tree Generator Pro"; Flags: nowait postinstall

[UninstallDelete]
Type: files; Name: "{app}\settings.ini"
Type: files; Name: "{app}\app.log"
Type: filesandordirs; Name: "{app}\_internal"
Type: dirifempty; Name: "{app}"