@echo off
setlocal
cd /d "%~dp0"
if defined MISSILE_LAB_PYTHON goto explicit_python
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto use_py
if exist "%USERPROFILE%\anaconda3\python.exe" goto use_anaconda
python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto use_python
echo Python 3.10 or newer is required. Anaconda also works.
pause
exit /b 1
:use_py
py -3 "%~dp0export_replay.py" %*
goto finished
:use_python
python "%~dp0export_replay.py" %*
goto finished
:use_anaconda
set "MISSILE_LAB_PYTHON=%USERPROFILE%\anaconda3\python.exe"
:explicit_python
"%MISSILE_LAB_PYTHON%" "%~dp0export_replay.py" %*
:finished
pause
