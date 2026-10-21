#define AppName "OUTMAX Cut"
#ifndef AppVersion
#define AppVersion "1.3.0"
#endif
[Setup]
AppId={{59722AFB-A431-44DF-B79F-8DD2D4256CD2}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=OUTMAX
AppPublisherURL=https://github.com/divangames/outmax-cut
AppUpdatesURL=https://github.com/divangames/outmax-cut/releases/latest
DefaultDirName={localappdata}\Programs\OUTMAX Cut
DefaultGroupName=OUTMAX
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=OUTMAX-Cut-Setup-{#AppVersion}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\OUTMAX-Cut.exe
CloseApplications=yes
SetupLogging=yes
SetupIconFile=..\assets\icon.ico
ChangesAssociations=yes
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"
[Files]
Source: "..\dist\{#AppVersion}\OUTMAX-Cut\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\OUTMAX Cut"; Filename: "{app}\OUTMAX-Cut.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\OUTMAX Cut"; Filename: "{app}\OUTMAX-Cut.exe"; WorkingDir: "{app}"; Tasks: desktopicon
[Run]
Filename: "{app}\OUTMAX-Cut.exe"; Description: "Запустить OUTMAX Cut"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Classes\Directory\shell\OutmaxCut"; ValueType: string; ValueName: ""; ValueData: "Смонтировать видео для сайта"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\OutmaxCut"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OUTMAX-Cut.exe"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\OutmaxCut"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\OutmaxCut\command"; ValueType: string; ValueData: """{app}\OUTMAX-Cut.exe"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\OutmaxCut"; ValueType: string; ValueName: ""; ValueData: "Смонтировать видео для сайта"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\OutmaxCut"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OUTMAX-Cut.exe"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\OutmaxCut"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\OutmaxCut\command"; ValueType: string; ValueData: """{app}\OUTMAX-Cut.exe"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mov\shell\OutmaxCut"; ValueType: string; ValueName: ""; ValueData: "Смонтировать видео для сайта"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mov\shell\OutmaxCut"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OUTMAX-Cut.exe"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mov\shell\OutmaxCut"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mov\shell\OutmaxCut\command"; ValueType: string; ValueData: """{app}\OUTMAX-Cut.exe"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m4v\shell\OutmaxCut"; ValueType: string; ValueName: ""; ValueData: "Смонтировать видео для сайта"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m4v\shell\OutmaxCut"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OUTMAX-Cut.exe"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m4v\shell\OutmaxCut"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.m4v\shell\OutmaxCut\command"; ValueType: string; ValueData: """{app}\OUTMAX-Cut.exe"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mkv\shell\OutmaxCut"; ValueType: string; ValueName: ""; ValueData: "Смонтировать видео для сайта"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mkv\shell\OutmaxCut"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OUTMAX-Cut.exe"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mkv\shell\OutmaxCut"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mkv\shell\OutmaxCut\command"; ValueType: string; ValueData: """{app}\OUTMAX-Cut.exe"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.avi\shell\OutmaxCut"; ValueType: string; ValueName: ""; ValueData: "Смонтировать видео для сайта"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.avi\shell\OutmaxCut"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OUTMAX-Cut.exe"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.avi\shell\OutmaxCut"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.avi\shell\OutmaxCut\command"; ValueType: string; ValueData: """{app}\OUTMAX-Cut.exe"" --open ""%1"""
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webm\shell\OutmaxCut"; ValueType: string; ValueName: ""; ValueData: "Смонтировать видео для сайта"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webm\shell\OutmaxCut"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\OUTMAX-Cut.exe"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webm\shell\OutmaxCut"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webm\shell\OutmaxCut\command"; ValueType: string; ValueData: """{app}\OUTMAX-Cut.exe"" --open ""%1"""
