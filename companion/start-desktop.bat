@echo off
cd /d %~dp0
title xiaoke.ai desktop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-desktop.ps1"
