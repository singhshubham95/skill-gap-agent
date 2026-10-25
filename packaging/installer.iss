; M29 consumer installer — per-user, no admin, no system Python.
; Design: specs/15-desktop-companion.md §Installer and release pipeline.
; Build through packaging/build.ps1 (it passes AppVersion/SourceDir/OutputDir
; and the optional OpenStore/Signing defines).

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\SkillGapAgent"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef StoreUrl
  #define StoreUrl ""
#endif
#ifndef OpenStore
  #define OpenStore 0
#endif

[Setup]
AppId={{5AA4631C-B140-46AD-905E-AE4CED1894A6}
AppName=Skill-Gap Agent
AppVersion={#AppVersion}
AppPublisher=Skill-Gap Agent
AppPublisherURL=https://github.com/singhshubham95/skill-gap-agent
AppSupportURL=https://github.com/singhshubham95/skill-gap-agent/issues
DefaultDirName={localappdata}\Programs\SkillGapAgent
DefaultGroupName=Skill-Gap Agent
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableWelcomePage=yes
PrivilegesRequired=lowest
UsePreviousAppDir=yes
OutputDir={#OutputDir}
OutputBaseFilename=SkillGapAgent-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\SkillGapAgent.exe
UninstallDisplayName=Skill-Gap Agent
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no
RestartApplications=no
SetupLogging=yes

; build.ps1 adds /DSigning=1 and /Sskillgap=<signtool command> only when a
; certificate is configured; unsigned builds leave this block out.
#ifdef Signing
SignTool=skillgap
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start Skill-Gap Agent when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Skill-Gap Agent"; Filename: "{app}\SkillGapAgent.exe"
Name: "{group}\Uninstall Skill-Gap Agent"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Skill-Gap Agent"; Filename: "{app}\SkillGapAgent.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SkillGapAgent"; ValueData: """{app}\SkillGapAgent.exe"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\SkillGapAgent.exe"; Description: "Launch Skill-Gap Agent"; Flags: nowait postinstall skipifsilent
#if int(OpenStore) == 1
Filename: "{#StoreUrl}"; Description: "Open the Chrome Web Store to add the extension"; Flags: shellexec nowait postinstall skipifsilent
#endif

[Code]
procedure StopCompanion();
var
  ResultCode: Integer;
begin
  // The tray app has no main window for Restart Manager to close. Install
  // (update) and uninstall are explicit actions; stop it before files move.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM SkillGapAgent.exe /F',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1500);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if FileExists(ExpandConstant('{localappdata}\Programs\SkillGapAgent\SkillGapAgent.exe')) then
    StopCompanion();
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  StopCompanion();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\SkillGapAgent');
    if (not UninstallSilent) and DirExists(DataDir) then
    begin
      if MsgBox('Also delete your Skill-Gap Agent data?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Choose No to keep your resume, saved sessions and analysis.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
