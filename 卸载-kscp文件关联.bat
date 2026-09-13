@echo off
rem ===========================================================================
rem  Remove the .kscp file association registered by the install bat.
rem
rem  Safe by design: it only touches the keys this project wrote under HKCU,
rem  and it refuses to remove the .kscp extension itself if some other program
rem  has claimed it in the meantime.
rem
rem  NOTE: this file is intentionally pure ASCII. cmd.exe reads a .bat in the
rem  console codepage, so non-ASCII text here would be garbled. All Chinese
rem  output comes from tools\kscp_assoc.py (run with PYTHONUTF8=1 below).
rem ===========================================================================
chcp 65001 >nul
setlocal
title KScript - Uninstall .kscp association

set "ROOT=%~dp0"
set "PY="

rem --- locate an interpreter: project venv first, then PATH ---
if exist "%ROOT%.venv\Scripts\python.exe" set "PY=%ROOT%.venv\Scripts\python.exe"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py"
)
if not defined PY (
    echo [ERROR] No Python interpreter found, cannot clean the registry.
    echo         Open a terminal in this folder and run:  uv sync
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%tools\kscp_assoc.py" (
    echo [ERROR] tools\kscp_assoc.py is missing next to this file.
    echo         Run this bat from the project root folder.
    echo.
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
"%PY%" "%ROOT%tools\kscp_assoc.py" uninstall %*
set "RC=%ERRORLEVEL%"

echo.
pause
exit /b %RC%
