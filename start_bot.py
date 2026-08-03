"""Launcher for Quotex bot - handles Python 3.14+ Windows asyncio compat."""
import sys
import asyncio
import os

# Fix for Python 3.14+ Windows: ensure there's always an event loop
if sys.platform == "win32":
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runpy
script = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "skills", "quotex-trader", "scripts", "quotex_bot.py"
)
runpy.run_path(script, run_name="__main__")
