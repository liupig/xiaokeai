@echo off
setlocal
py -3 -c "import sys; sys.exit(sys.version_info < (3,8))" >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0install.py" %*
  goto done
)
python -c "import sys; sys.exit(sys.version_info < (3,8))" >nul 2>nul
if not errorlevel 1 (
  python "%~dp0install.py" %*
  goto done
)
echo Python 3.8+ is required for this installer. See the included manual copy instructions.
pause
exit /b 1
:done
set "install_status=%ERRORLEVEL%"
if not "%install_status%"=="0" pause
exit /b %install_status%
