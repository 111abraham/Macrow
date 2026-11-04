@echo off
set SCRIPT_DIR=%~dp0
set PYTHON_EXE=%SCRIPT_DIR%..\.venv\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

"%PYTHON_EXE%" "%SCRIPT_DIR%sync_models.py" %*
pause
