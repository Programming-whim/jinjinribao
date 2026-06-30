@echo off
chcp 65001 >nul
echo ===========================================
echo  牛马工具2.0 - 一键打包安装包
echo ===========================================
echo.

echo [1/5] 隔离旧版本程序...
if exist "C:\Program Files\牛马工具2.0\牛马工具2.0.exe" (
    echo 发现旧版本程序，正在重命名为 .disabled...
    rename "C:\Program Files\牛马工具2.0\牛马工具2.0.exe" "牛马工具2.0.exe.disabled" 2>nul
    if %errorlevel%==0 (
        echo ✓ 旧版本已隔离
    ) else (
        echo ! 旧版本隔离失败（可能需要管理员权限）
    )
) else (
    echo - 未发现旧版本程序，跳过
)
echo.

echo [2/5] 终止残留进程...
taskkill /F /IM "牛马工具2.0.exe" 2>nul
if %errorlevel%==0 (
    echo ✓ 已终止牛马工具进程
) else (
    echo - 无残留进程
)
echo.

echo [3/5] 等待文件锁释放...
timeout /t 2 /nobreak >nul
echo ✓ 等待完成
echo.

echo [4/5] 打包EXE...
cd /d "%~dp0"
python -m PyInstaller "牛马工具.spec" --noconfirm

if not %errorlevel%==0 (
    echo.
    echo ===========================================
    echo  ✗ EXE打包失败，终止流程
    echo ===========================================
    echo.
    pause
    exit /b 1
)

echo ✓ EXE打包成功
echo.

echo [5/5] 打包安装包...
set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC_PATH%" (
    "%ISCC_PATH%" "installer.iss"
    if %errorlevel%==0 (
        echo.
        echo ===========================================
        echo  ✓ 安装包打包成功！
        echo  输出文件：installer_output\牛马工具2.0_安装包.exe
        echo ===========================================
    ) else (
        echo.
        echo ===========================================
        echo  ✗ 安装包打包失败，请检查错误信息
        echo ===========================================
    )
) else (
    echo.
    echo ===========================================
    echo  ✗ 未找到 Inno Setup 6
    echo  请先安装：winget install JRSoftware.InnoSetup
    echo ===========================================
)

echo.
pause
