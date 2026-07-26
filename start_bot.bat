@echo off
cd /d "C:\Users\PC\Desktop\Quotex Signal"
".venv\Scripts\python.exe" "skills\quotex-trader\scripts\quotex_bot.py" >> "bot_out.log" 2>> "bot_err.log"
