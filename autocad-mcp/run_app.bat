@echo off
title AutoCAD 2022 MCP Controller Launcher
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================================
echo   KHOI DONG UNG DUNG DIEU KHIEN AUTOCAD 2022 MCP HUB
echo ========================================================
echo Dang mo giao dien ung dung...
start pythonw app.py
if %ERRORLEVEL% NEQ 0 (
    python app.py
)
exit
