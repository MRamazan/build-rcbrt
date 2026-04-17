[Setup]
AppName=Recbert AI
AppVersion=1.0.0
DefaultDirName={autopf}\Recbert AI
DefaultGroupName=Recbert AI
OutputBaseFilename=RecbertAI-Setup
UninstallDisplayName=Recbert AI
UninstallDisplayIcon={app}\Recbert AI.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Tasks]
Name: desktopicon; Description: "Create desktop shortcut"

[Files]
Source: "dist\win-unpacked\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "python-embed\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs
Source: "python-embed\get-pip.py"; DestDir: "{app}\python"; Flags: ignoreversion
Source: "main_local.py"; DestDir: "{app}\backend"
Source: "utils.py"; DestDir: "{app}\backend"
Source: "options.py"; DestDir: "{app}\backend"
Source: "config.py"; DestDir: "{app}\backend"
Source: "loggers.py"; DestDir: "{app}\backend"
Source: "templates.py"; DestDir: "{app}\backend"
Source: "requirements.txt"; DestDir: "{app}\backend"
Source: "models\*"; DestDir: "{app}\backend\models"; Flags: recursesubdirs
Source: "dataloaders\*"; DestDir: "{app}\backend\dataloaders"; Flags: recursesubdirs
Source: "trainers\*"; DestDir: "{app}\backend\trainers"; Flags: recursesubdirs
Source: "datasets\*"; DestDir: "{app}\backend\datasets"; Flags: recursesubdirs
Source: "Data\*"; DestDir: "{app}\backend\Data"; Flags: recursesubdirs

[Icons]
Name: "{group}\Recbert AI"; Filename: "{app}\Recbert AI.exe"; IconFilename: "{app}\Recbert AI.exe"; IconIndex: 0
Name: "{commondesktop}\Recbert AI"; Filename: "{app}\Recbert AI.exe"; Tasks: desktopicon; IconFilename: "{app}\Recbert AI.exe"; IconIndex: 0

[Code]
procedure RunStep(const Label_, Python, Params, LogFile: String);
var
  ResultCode: Integer;
  Cmd: String;
begin
  SaveStringToFile(LogFile, '[' + Label_ + '] Running: "' + Python + '" ' + Params + #13#10, True);
  Cmd := '/c ""' + Python + '" ' + Params + ' >> "' + LogFile + '" 2>&1"';
  Exec(ExpandConstant('{sys}\cmd.exe'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  SaveStringToFile(LogFile, '[' + Label_ + '] Exit code: ' + IntToStr(ResultCode) + #13#10, True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir, BackendPath, PythonExe, ConfigPath, LogFile, Content: String;
begin
  if CurStep = ssPostInstall then
  begin
    AppDir      := ExpandConstant('{app}');
    BackendPath := AppDir + '\backend';
    PythonExe   := AppDir + '\python\python.exe';
    ConfigPath  := AppDir + '\resources\app\config.json';
    LogFile     := AppDir + '\install.log';

    SaveStringToFile(LogFile, '=== Recbert AI Install Log ===' + #13#10, False);
    SaveStringToFile(LogFile, 'AppDir: ' + AppDir + #13#10, True);
    SaveStringToFile(LogFile, 'PythonExe: ' + PythonExe + #13#10, True);

    if not FileExists(PythonExe) then
    begin
      SaveStringToFile(LogFile, 'FATAL: python.exe not found at ' + PythonExe + #13#10, True);
      MsgBox('Installation failed: python.exe not found at:' + #13#10 + PythonExe, mbError, MB_OK);
      Exit;
    end;

    WizardForm.StatusLabel.Caption := 'Installing pip...';
    RunStep('pip', PythonExe, '"' + AppDir + '\python\get-pip.py" --no-warn-script-location', LogFile);

    WizardForm.StatusLabel.Caption := 'Installing PyTorch (CPU)... This may take a few minutes...';
    RunStep('torch', PythonExe, '-m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu --no-warn-script-location', LogFile);

    WizardForm.StatusLabel.Caption := 'Installing dependencies...';
    RunStep('requirements', PythonExe, '-m pip install -r "' + BackendPath + '\requirements.txt" --no-warn-script-location', LogFile);

    WizardForm.StatusLabel.Caption := 'Installing additional tools...';
    RunStep('tools', PythonExe, '-m pip install setuptools --no-warn-script-location', LogFile);

    WizardForm.StatusLabel.Caption := 'Verifying installation...';
    RunStep('verify-flask', PythonExe, '-c "import flask; print(''flask'', flask.__version__)"', LogFile);
    RunStep('verify-torch', PythonExe, '-c "import torch; print(''torch'', torch.__version__)"', LogFile);

    SaveStringToFile(LogFile, 'Writing config.json...' + #13#10, True);
    StringChangeEx(BackendPath, '\', '\\', True);
    StringChangeEx(PythonExe,   '\', '\\', True);
    Content :=
      '{' +
        '"backendPath": "'      + BackendPath + '", ' +
        '"pythonExecutable": "' + PythonExe   + '", ' +
        '"flaskPort": 5000, '   +
        '"autoStartBackend": true' +
      '}';
    SaveStringToFile(ConfigPath, Content, False);

    SaveStringToFile(LogFile, '=== Install complete ===' + #13#10, True);
  end;
end;
