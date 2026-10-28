; Both complete payloads are embedded; native OS architecture selects exactly one.
#ifndef Amd64Bundle
  #error Amd64Bundle is required
#endif
#ifndef Arm64Bundle
  #error Arm64Bundle is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef RuntimeProbe
  #error RuntimeProbe is required
#endif

[Setup]
#ifdef TestBuild
AppId=ArcadeClip-Installer-Fixture
CreateUninstallRegKey=no
#else
; Preserve the previous ARM64 installer identity for in-place upgrades.
AppId={{33CE480B-F420-4C23-985C-E721563A135F}
#endif
AppName=ArcadeClip
AppVersion={#AppVersion}
AppPublisher=ParkoutV / ArcadeClip community
AppPublisherURL=https://github.com/ParkoutV/ArcadeClip
DefaultDirName={localappdata}\Programs\ArcadeClip
DefaultGroupName=ArcadeClip
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os or (arm64 and x64compatible)
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=ArcadeClip-{#AppVersion}-windows-universal-user-setup
SetupIconFile={#Amd64Bundle}\src\assets\icon.ico
UninstallDisplayIcon={app}\ArcadeClip.exe
LicenseFile={#Amd64Bundle}\INSTALLER-LICENSE.txt
InfoAfterFile=INSTALL-NOTES.txt
WizardStyle=modern
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=2
DiskSpanning=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "startmenuicon"; Description: "{cm:StartMenuRegistration}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[CustomMessages]
english.StartMenuRegistration=Register ArcadeClip in the Start menu / All apps
korean.StartMenuRegistration=시작 메뉴 / 모든 앱 목록에 ArcadeClip 등록
english.RuntimeTitle=Python and FFmpeg
korean.RuntimeTitle=Python 및 FFmpeg 선택
english.PythonDescription=Choose the app Python runtime
korean.PythonDescription=앱을 실행할 Python을 선택하세요
english.PythonDetails=Compatible CPython 3.13 on PATH is recommended when available.%nApp dependencies stay private. The isolated x64 OCR Python is always included.
korean.PythonDetails=PATH에 호환되는 CPython 3.13이 있으면 로컬 사용을 권장합니다.%n앱 패키지는 별도로 제공하며, 격리된 x64 OCR Python은 항상 포함합니다.
english.FFmpegDescription=Choose FFmpeg command-line tools
korean.FFmpegDescription=FFmpeg 명령줄 도구를 선택하세요
english.FFmpegDetails=Local FFmpeg requires ffprobe in the same folder and working H.264/AAC encoders.%nQt/PyAV media libraries are always included. Global PATH is never changed.
korean.FFmpegDetails=로컬 FFmpeg는 같은 폴더의 ffprobe 및 H.264/AAC 인코더가 필요합니다.%nQt/PyAV 미디어 라이브러리는 항상 포함하며, 시스템 PATH는 변경하지 않습니다.
english.BundledPython=Include Python in ArcadeClip (works independently)
korean.BundledPython=Python을 프로그램에 내장 (독립 실행)
english.BundledFFmpeg=Include FFmpeg in ArcadeClip (works independently)
korean.BundledFFmpeg=FFmpeg를 프로그램에 내장 (독립 실행)
english.LocalRecommended=Use compatible local installation (recommended): %1
korean.LocalRecommended=호환되는 로컬 설치 사용 (권장): %1
english.LocalUnavailable=No compatible installation found on PATH; bundled runtime recommended
korean.LocalUnavailable=PATH에서 호환되는 설치를 찾지 못했습니다. 내장 사용을 권장합니다
english.RuntimeMissing=The selected local runtime is no longer usable. Select the bundled option.
korean.RuntimeMissing=선택한 로컬 런타임을 사용할 수 없습니다. 내장 옵션을 선택하세요.

[InstallDelete]
; These folders contain application-owned files, never profiles or recordings.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\tools"
Type: files; Name: "{app}\arm64-portable.json"
Type: filesandordirs; Name: "{app}\src\__pycache__"
Type: files; Name: "{app}\src\assets\gpu_roi_*.dll"

[Files]
Source: "{#RuntimeProbe}"; DestName: "runtime-probe.exe"; Flags: dontcopy
; App code, OCR helper and notices are always installed.
Source: "{#Arm64Bundle}\*"; DestDir: "{app}"; Excludes: "runtime\*,tools\*,__pycache__\*,*.pyc,*.pyo,*.pdb,*.lib"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: NativeArm64
Source: "{#Arm64Bundle}\runtime\Lib\*"; DestDir: "{app}\runtime\Lib"; Excludes: "*.pyc,__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: NativeArm64
Source: "{#Arm64Bundle}\runtime\*"; DestDir: "{app}\runtime"; Excludes: "Lib\*"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: ArmPython
Source: "{#Arm64Bundle}\tools\*"; DestDir: "{app}\tools"; Excludes: "deno.exe"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: ArmFFmpeg
Source: "{#Arm64Bundle}\tools\deno.exe"; DestDir: "{app}\tools"; Flags: ignoreversion; Check: NativeArm64
Source: "{#Amd64Bundle}\*"; DestDir: "{app}"; Excludes: "runtime\*,tools\*,__pycache__\*,*.pyc,*.pyo,*.pdb,*.lib"; Flags: ignoreversion recursesubdirs createallsubdirs solidbreak; Check: not NativeArm64
Source: "{#Amd64Bundle}\runtime\Lib\*"; DestDir: "{app}\runtime\Lib"; Excludes: "*.pyc,__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: not NativeArm64
Source: "{#Amd64Bundle}\runtime\*"; DestDir: "{app}\runtime"; Excludes: "Lib\*"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: AmdPython
Source: "{#Amd64Bundle}\tools\*"; DestDir: "{app}\tools"; Excludes: "deno.exe"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: AmdFFmpeg
Source: "{#Amd64Bundle}\tools\deno.exe"; DestDir: "{app}\tools"; Flags: ignoreversion; Check: not NativeArm64
Source: "INSTALL-NOTES.txt"; DestDir: "{app}"; Flags: ignoreversion solidbreak

[Icons]
Name: "{userprograms}\ArcadeClip\ArcadeClip"; Filename: "{app}\ArcadeClip.exe"; WorkingDir: "{app}"; Tasks: startmenuicon
Name: "{userprograms}\ArcadeClip\Uninstall ArcadeClip"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{userdesktop}\ArcadeClip"; Filename: "{app}\ArcadeClip.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ArcadeClip.exe"; Description: "{cm:LaunchProgram,ArcadeClip}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\runtime-config.ini"

[Code]
var
  PythonPage, FFmpegPage: TInputOptionWizardPage;
  LocalPython, LocalFFmpeg, Probe, Arch: String;

function NativeArm64(): Boolean;
begin
#ifdef TestBuild
  Result := '{#TestArchitecture}' = 'arm64';
#else
  Result := IsArm64;
#endif
end;

function ProbeRuntime(Kind, Filename: String): Boolean;
var
  Code: Integer;
begin
  Result := False;
  if not FileExists(Filename) then exit;
  try
    Result := Exec(Probe, Kind + ' "' + Filename + '" ' + Arch, '', SW_HIDE,
      ewWaitUntilTerminated, Code) and (Code = 0);
  except
    Log(GetExceptionMessage);
  end;
end;

function CompatibleFFmpeg(Directory: String): Boolean;
begin
  Result := ProbeRuntime('ffprobe', AddBackslash(Directory) + 'ffprobe.exe') and
    ProbeRuntime('ffmpeg', AddBackslash(Directory) + 'ffmpeg.exe');
end;

function FindRuntime(Kind: String): String;
var
  Remaining, Directory, Candidate: String;
  Separator: Integer;
begin
  Result := '';
  Remaining := GetEnv('PATH') + ';';
  while Remaining <> '' do begin
    Separator := Pos(';', Remaining);
    Directory := RemoveQuotes(Trim(Copy(Remaining, 1, Separator - 1)));
    Delete(Remaining, 1, Separator);
    if (Directory <> '') and (Pos('\windowsapps', Lowercase(Directory)) = 0) then begin
      Candidate := AddBackslash(Directory) + Kind + '.exe';
      if FileExists(Candidate) then begin
        if Kind = 'python' then begin
          if ProbeRuntime(Kind, Candidate) then begin Result := Candidate; exit; end;
        end else if CompatibleFFmpeg(Directory) then begin Result := Directory; exit; end;
      end;
    end;
  end;
end;

procedure InitializeWizard();
var
  Previous, Config: String;
begin
  if NativeArm64 then Arch := 'arm64' else Arch := 'amd64';
  ExtractTemporaryFile('runtime-probe.exe');
  Probe := ExpandConstant('{tmp}\runtime-probe.exe');
  LocalPython := FindRuntime('python');
  LocalFFmpeg := FindRuntime('ffmpeg');
  Config := ExpandConstant('{param:DIR|}');
  if Config = '' then
    RegQueryStringValue(HKCU64, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{33CE480B-F420-4C23-985C-E721563A135F}_is1', 'InstallLocation', Config);
  if Config = '' then Config := ExpandConstant('{localappdata}\Programs\ArcadeClip');
  Config := AddBackslash(Config) + 'runtime-config.ini';
  Previous := GetIniString('Runtime', 'Python', '', Config);
  if (Previous <> '') and ProbeRuntime('python', Previous) then LocalPython := Previous;
  PythonPage := CreateInputOptionPage(wpSelectDir, CustomMessage('RuntimeTitle'),
    CustomMessage('PythonDescription'), CustomMessage('PythonDetails'), True, False);
  PythonPage.Add(CustomMessage('BundledPython'));
  if LocalPython <> '' then
    PythonPage.Add(FmtMessage(CustomMessage('LocalRecommended'), [LocalPython]))
  else PythonPage.Add(CustomMessage('LocalUnavailable'));
  PythonPage.CheckListBox.ItemEnabled[1] := LocalPython <> '';
  PythonPage.SelectedValueIndex := 0;
  if (LocalPython <> '') and ((not WizardSilent) or (Previous = LocalPython)) then
    PythonPage.SelectedValueIndex := 1;
  Previous := GetIniString('Runtime', 'FFmpegDir', '', Config);
  if (Previous <> '') and CompatibleFFmpeg(Previous) then LocalFFmpeg := Previous;
  FFmpegPage := CreateInputOptionPage(PythonPage.ID, CustomMessage('RuntimeTitle'),
    CustomMessage('FFmpegDescription'), CustomMessage('FFmpegDetails'), True, False);
  FFmpegPage.Add(CustomMessage('BundledFFmpeg'));
  if LocalFFmpeg <> '' then
    FFmpegPage.Add(FmtMessage(CustomMessage('LocalRecommended'), [LocalFFmpeg]))
  else FFmpegPage.Add(CustomMessage('LocalUnavailable'));
  FFmpegPage.CheckListBox.ItemEnabled[1] := LocalFFmpeg <> '';
  FFmpegPage.SelectedValueIndex := 0;
  if (LocalFFmpeg <> '') and ((not WizardSilent) or (Previous = LocalFFmpeg)) then
    FFmpegPage.SelectedValueIndex := 1;
  if ExpandConstant('{param:PYTHON|}') = 'bundled' then PythonPage.SelectedValueIndex := 0;
  if ExpandConstant('{param:PYTHON|}') = 'local' then PythonPage.SelectedValueIndex := 1;
  if ExpandConstant('{param:FFMPEG|}') = 'bundled' then FFmpegPage.SelectedValueIndex := 0;
  if ExpandConstant('{param:FFMPEG|}') = 'local' then FFmpegPage.SelectedValueIndex := 1;
end;

function ArmPython(): Boolean;
begin Result := NativeArm64 and (PythonPage.SelectedValueIndex = 0); end;
function AmdPython(): Boolean;
begin Result := not NativeArm64 and (PythonPage.SelectedValueIndex = 0); end;
function ArmFFmpeg(): Boolean;
begin Result := NativeArm64 and (FFmpegPage.SelectedValueIndex = 0); end;
function AmdFFmpeg(): Boolean;
begin Result := not NativeArm64 and (FFmpegPage.SelectedValueIndex = 0); end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if (PythonPage.SelectedValueIndex = 1) and not ProbeRuntime('python', LocalPython) then
    Result := CustomMessage('RuntimeMissing');
  if (FFmpegPage.SelectedValueIndex = 1) and not CompatibleFFmpeg(LocalFFmpeg) then
    Result := CustomMessage('RuntimeMissing');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Config, PythonValue, FFmpegValue: String;
  BOM: AnsiString;
begin
  if CurStep = ssPostInstall then begin
    PythonValue := '';
    FFmpegValue := '';
    if PythonPage.SelectedValueIndex = 1 then PythonValue := LocalPython;
    if FFmpegPage.SelectedValueIndex = 1 then FFmpegValue := LocalFFmpeg;
    Config := ExpandConstant('{app}\runtime-config.ini');
    BOM := '  ';
    BOM[1] := #255;
    BOM[2] := #254;
    if not SaveStringToFile(Config, BOM, False) or
      not SetIniString('Runtime', 'Python', PythonValue, Config) or
      not SetIniString('Runtime', 'FFmpegDir', FFmpegValue, Config) or
      not SetIniString('Runtime', 'Architecture', Arch, Config) then
      RaiseException('Could not save runtime configuration.');
  end;
end;

