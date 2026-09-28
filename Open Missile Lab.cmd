@echo off
setlocal
cd /d "%~dp0"
if defined MISSILE_LAB_PYTHON goto explicit_python
py -3 -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto use_py
if exist "%USERPROFILE%\anaconda3\python.exe" goto use_anaconda
python -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto use_python
goto missing_python

:use_py
py -3 "%~dp0configurator.py"
goto finished

:use_python
python "%~dp0configurator.py"
goto finished

:use_anaconda
set "MISSILE_LAB_PYTHON=%USERPROFILE%\anaconda3\python.exe"
:explicit_python
if not exist "%MISSILE_LAB_PYTHON%" goto missing_python
"%MISSILE_LAB_PYTHON%" "%~dp0configurator.py"
:finished
if errorlevel 1 pause
exit /b

:missing_python
echo Python 3.10 or newer with Tkinter is required.
echo Install Python with Tcl/Tk support, or set MISSILE_LAB_PYTHON to python.exe.
pause
exit /b 1
