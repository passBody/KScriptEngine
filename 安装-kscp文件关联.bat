@echo off
rem ===========================================================================
rem  Install the .kscp file association for THIS copy of the project.
rem
rem  What it does: registers the absolute path of this folder's main.py so that
rem  double-clicking (or right-clicking) a .kscp file opens it with KScript,
rem  using the icon in icon\kscp.ico.
rem
rem  Moved the project to another folder? Run the UNINSTALL bat in the old
rem  folder first, then this INSTALL bat in the new one.
rem
rem  NOTE: this file is intentionally pure ASCII. cmd.exe reads a .bat in the
rem  console codepage, so non-ASCII text here would be garbled. All Chinese
rem  output comes from tools\kscp_assoc.py (run with PYTHONUTF8=1 below).
rem ===========================================================================
chcp 65001 >nul
setlocal
title KScript - Install .kscp association

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
    echo [ERROR] No Python interpreter found.
    echo         Open a terminal in this folder and run:  uv sync
    echo         (or install Python 3.14+ and make sure it is on PATH^)
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
"%PY%" "%ROOT%tools\kscp_assoc.py" install %*
set "RC=%ERRORLEVEL%"

echo.
pause
exit /b %RC%
