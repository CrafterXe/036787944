@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Math Notes Assistant - Install
echo.

rem 优先使用 py 启动器，其次 python / python3
set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD ( where python >nul 2>nul && set "PYCMD=python" )
if not defined PYCMD ( where python3 >nul 2>nul && set "PYCMD=python3" )

if not defined PYCMD (
    echo [ERROR] Python not found. Please install Python 3.10+ first:
    echo         https://www.python.org/downloads/
    echo         ^(During install, tick "Add Python to PATH"^)
    echo.
    pause
    exit /b 1
)

%PYCMD% "%~dp0install.py"
echo.
pause
