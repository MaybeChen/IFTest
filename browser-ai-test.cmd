@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
set "VENV_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
  echo [ERROR] Virtual environment Python not found: "%VENV_PYTHON%"
  echo Create it first with: py -3.12 -m venv .venv
  exit /b 1
)

set "PYTHONPATH=%PROJECT_ROOT%src;%PYTHONPATH%"
"%VENV_PYTHON%" -m browser_ai_test.cli %*
exit /b %ERRORLEVEL%
