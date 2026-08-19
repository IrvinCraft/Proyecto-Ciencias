; Inno Setup installer para Quiz Educativo.
; Se compila en GitHub Actions (windows-latest) tras el build de PyInstaller
; onedir. Instala SIN permisos de administrador en la carpeta del usuario,
; de modo que la app pueda auto-actualizarse en sitio (no se acumulan .exe).
; Uso:  ISCC.exe installer.iss /DMyAppVersion=1.0.3

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "Quiz Educativo"
#define MyAppExeName "QuizEducativo.exe"

[Setup]
AppId=ProyectoCiencias-QuizEducativo
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Proyecto-Ciencias
DefaultDirName={localappdata}\QuizEducativo
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=QuizEducativo-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
UninstallDisplayName={#MyAppName}
WizardStyle=modern

[Files]
Source: "dist\QuizEducativo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Quiz Educativo"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Quiz Educativo"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar Quiz Educativo"; Flags: nowait postinstall skipifsilent