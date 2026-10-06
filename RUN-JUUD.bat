@echo off
rem Start a locally recorded Juud build with the two measured opt-in engine changes.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Juud setup is missing. First run START-HERE.bat --setup --build --no-start
  exit /b 1
)
".venv\Scripts\python.exe" tools\check_juud_build.py
if errorlevel 1 exit /b 1
set "STRATA_POOL_SPIN_US="
set "JUUD_POOL_ADAPTIVE_SPIN=1"
set "JUUD_SKIP_UNUSED_ACTQ=1"
set "JUUD_REQUIRE_SOURCE_BUILD=1"
set "PYTHONUTF8=1"
call START-HERE.bat %*
exit /b %errorlevel%
