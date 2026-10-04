@echo off
rem Skill-Gap Agent - local server launcher (M14).
rem Double-click to start the local agent that the Chrome extension talks to.
rem Extra arguments are passed through, e.g.:
rem   start-server.bat --port 8000 --skills C:\path\to\resume.pdf
cd /d "%~dp0.."

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY set "PY=python"

echo Starting Skill-Gap Agent server on http://127.0.0.1:8000 ...
echo Close this window to stop the server.
echo.

%PY% -m skill_gap_agent.server %*
if errorlevel 1 (
  echo.
  echo The server exited with an error - see the message above.
  pause
)
