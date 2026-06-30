; 牛马工具2 - Inno Setup 安装脚本

#define MyAppName "牛马工具2.0"
#define MyAppVersion "2.4.6"
#define MyAppPublisher "wbw"
#define MyAppExeName "牛马工具2.0.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=牛马工具2.0_安装包
SetupIconFile=logo.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayName={#MyAppName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
english.WelcomeLabel1=欢迎安装 {#MyAppName}
english.WelcomeLabel2=本向导将安装 {#MyAppName} 到您的电脑上。%n%n点击"下一步"继续安装，或点击"取消"退出安装。
english.SelectDirLabel3=安装程序将把 {#MyAppName} 安装到以下目录。%n%n如需安装到其他位置，请点击"浏览"。
english.SelectDirBrowseLabel=安装程序将把 {#MyAppName} 安装到以下目录。%n%n如需安装到其他位置，请点击"浏览"。
english.SelectTasksLabel2=选择安装时需要执行的附加任务。%n%n点击"下一步"继续，或点击"上一步"修改选择。
english.ReadyLabel1=安装程序已准备好开始安装 {#MyAppName}。%n%n点击"安装"继续，或点击"上一步"修改设置。
english.ReadyLabel2a=安装程序已准备好开始安装 {#MyAppName}。%n%n点击"安装"继续，或点击"上一步"修改设置。
english.FinishedHeadingLabel=安装完成
english.FinishedLabel=安装程序已在您的电脑上完成 {#MyAppName} 的安装。%n%n点击"完成"退出安装向导。
english.ConfirmUninstall=确认卸载 {#MyAppName}？%n%n点击"是"继续卸载，点击"否"取消。
english.UninstalledAll={#MyAppName} 已成功从您的电脑上卸载。
english.ButtonNext=下一步(&N)
english.ButtonBack=上一步(&B)
english.ButtonInstall=安装(&I)
english.ButtonFinish=完成(&F)
english.ButtonCancel=取消(&C)
english.ButtonYes=是(&Y)
english.ButtonNo=否(&N)
english.ButtonBrowse=浏览(&B)
english.WizardSelectTasks=选择附加任务
english.WizardReady=准备安装

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"
Name: "startmenuicon"; Description: "创建开始菜单快捷方式"; GroupDescription: "附加选项:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
