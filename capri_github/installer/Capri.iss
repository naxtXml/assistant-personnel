; Script Inno Setup pour Capri -> produit installer\Output\CapriSetup.exe
#define MyAppName "Capri"
#define MyAppVersion "1.0.0"
#define MyAppExe "Capri.exe"

[Setup]
AppId={{418EE6D9-BF6E-4190-B654-36EA1BA1D488}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Nathan
DefaultDirName={localappdata}\Programs\Capri
DefaultGroupName=Capri
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=CapriSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExe}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"
Name: "startup"; Description: "Lancer Capri au démarrage de Windows"; GroupDescription: "Options :"; Flags: unchecked

[Files]
; Tout le contenu produit par PyInstaller (Python et bibliothèques inclus)
Source: "..\dist\Capri\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; HUD C# facultatif : copie dist\CapriDesktop\ s'il a été compilé (voir README)
Source: "..\dist\CapriDesktop\*"; DestDir: "{app}\CapriDesktop"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\Capri"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Serveur Capri"; Filename: "{app}\{#MyAppExe}"; Parameters: "--serveur"
Name: "{group}\Désinstaller Capri"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Capri"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon
Name: "{userstartup}\Capri"; Filename: "{app}\{#MyAppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Lancer Capri maintenant"; Flags: nowait postinstall skipifsilent
