@echo off

chcp 65001 >nul

cd /d "%~dp0"

title PRISM Benchmark (full run)

echo.

echo Starting PRISM full benchmark — do not close this window.

echo.

python "%~dp0run_prism_benchmark.py"

set EXITCODE=%ERRORLEVEL%

echo.

if %EXITCODE% neq 0 (

  echo Finished with exit code: %EXITCODE%

) else (

  echo Finished successfully.

)

echo.

pause

