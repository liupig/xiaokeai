@echo off
cd /d %~dp0
title MiniCPM-V 4.7
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
