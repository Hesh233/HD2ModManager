@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
rem Canonical launcher for the installed skeleton-test manager.
rem Examples: -CheckOnly, -Mode Startup, -OutputDirectory "D:\Package Output"
set "HD2_PACKAGE_INSTALLATION_ROOT=%~dp0."
set "packager=%~dp0非运行文件\打包工具\Package-Manager.ps1"
if not exist "%packager%" goto missing_tools
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%packager%" %*
set "rc=%errorlevel%"
goto done
:missing_tools
echo Packaging tools are missing: "%packager%"
echo Synchronize the packaging launcher and tools before retrying.
set "rc=2"
:done
echo.
if not "%rc%"=="0" echo Packaging failed. See the error above. Any .partial file is NOT a finished ZIP.
if not defined HD2_PACKAGE_NO_PAUSE pause
exit /b %rc%
