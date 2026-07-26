@echo off
cd /d "C:\Users\PC\Desktop\Quotex Signal"
set MAX_RETRIES=6
set RETRY_DELAY=30
set TRY=1

:retry
echo [%date% %time%] Attempt %TRY%/%MAX_RETRIES% >> "bot_watchdog.log"
".venv\Scripts\python.exe" "skills\quotex-trader\scripts\quotex_bot.py" >> "bot_out.log" 2>> "bot_err.log"
if %ERRORLEVEL% NEQ 0 (
    if %TRY% LSS %MAX_RETRIES% (
        set /a TRY+=1
        timeout /t %RETRY_DELAY% /nobreak >nul
        goto retry
    )
)
echo [%date% %time%] Exhausted retries, giving up >> "bot_watchdog.log"
