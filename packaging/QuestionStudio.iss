#define ReleaseStage GetEnv("QUESTION_STUDIO_RELEASE_STAGE")
#define ReleaseOutput GetEnv("QUESTION_STUDIO_RELEASE_OUTPUT")
#define RequirementsInfo SourcePath + "\requirements-message.txt"

[Setup]
AppId={{3C24F521-2636-4B44-BE3D-6947866D3950}
AppName=Question Studio
AppVersion=1.0.0
AppVerName=Question Studio 1.0.0
AppPublisher=Question Studio
DefaultDirName={localappdata}\Programs\QuestionStudio
DefaultGroupName=Question Studio
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
SetupIconFile={#ReleaseStage}\app\static\favicon.ico
UninstallDisplayIcon={app}\QuestionStudio.exe
InfoBeforeFile={#RequirementsInfo}
OutputDir={#ReleaseOutput}
OutputBaseFilename=QuestionStudio-1.0.0-windows-x64-setup
Compression=lzma2/ultra64
SolidCompression=yes
Uninstallable=yes
CloseApplications=yes
RestartApplications=no
RestartIfNeededByRun=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#ReleaseStage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Question Studio"; Filename: "{app}\QuestionStudio.exe"
Name: "{autodesktop}\Question Studio"; Filename: "{app}\QuestionStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\QuestionStudio.exe"; Description: "Launch Question Studio"; Flags: nowait postinstall skipifsilent

[Code]
function TryStopInstalledQuestionStudio(var ErrorMessage: String): Boolean;
var
  PythonwPath: String;
  DesktopScriptPath: String;
  Params: String;
  ResultCode: Integer;
begin
  Result := True;
  ErrorMessage := '';
  PythonwPath := ExpandConstant('{app}\runtime\python\pythonw.exe');
  DesktopScriptPath := ExpandConstant('{app}\app\desktop.py');

  { A fresh install has no previous runtime to stop. }
  if not FileExists(PythonwPath) or not FileExists(DesktopScriptPath) then
    Exit;

  Params := '"' + DesktopScriptPath + '" --stop';
  if not Exec(PythonwPath, Params, ExpandConstant('{app}'), SW_HIDE,
      ewWaitUntilTerminated, ResultCode) then
  begin
    Result := False;
    ErrorMessage := '기존 Question Studio 서버를 종료하지 못했습니다. AI 작업이 실행 중이면 완료를 기다린 뒤 앱을 닫고 다시 시도해 주세요.';
    Exit;
  end;

  if ResultCode <> 0 then
  begin
    Result := False;
    ErrorMessage := 'Question Studio에서 실행 중인 작업을 종료하지 못했습니다. AI 작업이 완료될 때까지 기다린 뒤 앱을 닫고 다시 시도해 주세요.';
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ErrorMessage: String;
begin
  if TryStopInstalledQuestionStudio(ErrorMessage) then
    Result := ''
  else
    Result := ErrorMessage;
end;

function InitializeUninstall(): Boolean;
var
  ErrorMessage: String;
begin
  Result := TryStopInstalledQuestionStudio(ErrorMessage);
  if not Result then
    MsgBox(ErrorMessage + #13#10 + '제거를 계속하지 않았습니다.', mbError, MB_OK);
end;
