@echo off
setlocal

rem Open the dedicated Chrome profile used by cookie-export.py.
rem Log in to the sites you need, then close this Chrome window completely.

set "PROFILE_DIR=%LOCALAPPDATA%\tools\chrome-ytdlp"
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
    echo Chrome not found. Edit CHROME in this script.
    exit /b 1
)

start "" "%CHROME%" --user-data-dir="%PROFILE_DIR%"
