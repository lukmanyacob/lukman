@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY python --version >nul 2>&1 && set PY=python
if not defined PY (
  echo Python belum dipasang dalam komputer ini.
  echo Muat turun dari https://www.python.org/downloads/ dan tanda "Add Python to PATH" masa install.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)
echo Menyediakan sokongan backup ber-password...
%PY% -m pip install --quiet --disable-pip-version-check iphone_backup_decrypt >nul 2>&1
%PY% iphone_backup_extract.py %*
echo.
pause
