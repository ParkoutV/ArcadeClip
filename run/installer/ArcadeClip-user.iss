; Complete standalone bundle, per-user installation without elevation.
#ifndef BundleDir
  #error BundleDir must identify the verified ARM64 standalone folder
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by the build script
#endif

[Setup]
AppId={{33CE480B-F420-4C23-985C-E721563A135F}
AppName=ArcadeClip ARM64
AppVersion=0.2.1-performance.20261021.3
AppVerName=ArcadeClip ARM64 0.2.1 (Performance)
AppPublisher=ArcadeClip community build
VersionInfoVersion=0.2.1.1021
DefaultDirName={localappdata}\Programs\ArcadeClip-ARM64
DefaultGroupName=ArcadeClip ARM64
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=arm64 and x64compatible
ArchitecturesInstallIn64BitMode=arm64
MinVersion=10.0.22000
OutputDir={#OutputDir}
OutputBaseFilename=ArcadeClip-0.2.1-performance-20261021-r3-windows-arm64-user-setup
SetupIconFile={#BundleDir}\src\assets\icon.ico
UninstallDisplayIcon={app}\ArcadeClip.exe
UninstallDisplayName=ArcadeClip ARM64 (Performance)
LicenseFile={#BundleDir}\INSTALLER-LICENSE.txt
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
english.UpgradeDetected=Update mode: Existing version (%1) detected. Program files will be updated in place while preserving your data, profiles, and saved work.
korean.UpgradeDetected=업데이트 설치: 기존 설치본(%1)이 감지되었습니다. 사용자 데이터·프로필·작업 내역을 그대로 유지한 채 프로그램 파일만 새 버전으로 업데이트합니다.

[InstallDelete]
Type: filesandordirs; Name: "{app}\src\__pycache__"
Type: files; Name: "{app}\src\*.pyc"
Type: files; Name: "{app}\src\*.pyo"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Excludes: "__pycache__\*,*.pyc,*.pyo,*.pdb,*.lib"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "INSTALL-NOTES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\ArcadeClip ARM64\ArcadeClip"; Filename: "{app}\ArcadeClip.exe"; WorkingDir: "{app}"; IconFilename: "{app}\src\assets\icon.ico"; Tasks: startmenuicon
Name: "{userprograms}\ArcadeClip ARM64\Uninstall ArcadeClip"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{userdesktop}\ArcadeClip ARM64"; Filename: "{app}\ArcadeClip.exe"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\src\assets\icon.ico"

[Run]
Filename: "{app}\ArcadeClip.exe"; Description: "{cm:LaunchProgram,ArcadeClip}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
const
  UninstallRegKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{33CE480B-F420-4C23-985C-E721563A135F}_is1';

function GetInstalledVersion(): String;
begin
  if not RegQueryStringValue(HKCU, UninstallRegKey, 'DisplayVersion', Result) then
    Result := '';
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  PrevVer: String;
begin
  Result := '';
  PrevVer := GetInstalledVersion();
  if PrevVer <> '' then
    Result := Result + FmtMessage(CustomMessage('UpgradeDetected'), [PrevVer]) + NewLine + NewLine;
  if MemoDirInfo <> '' then
    Result := Result + MemoDirInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then
    Result := Result + MemoTasksInfo + NewLine + NewLine;
end;
