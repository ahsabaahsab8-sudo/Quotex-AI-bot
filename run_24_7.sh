#!/bin/bash
# Quotex Bot 24/7 Startup Script for VPS
# Run: bash run_24_7.sh

cd "$(dirname "$0")"

# Kill any existing bot processes
pkill -f "quotex_bot.py" 2>/dev/null || true
pkill -f "start_bot.py" 2>/dev/null || true
sleep 2

# Set environment
export NO_PROXY="googleapis.com,google.com"
export no_proxy="googleapis.com,google.com"

# Run bot with nohup (keeps running after logout)
echo "Starting Quotex bot 24/7..."
nohup python3 start_bot.py > bot.log 2>&1 &

echo "Bot PID: $!"
echo "Logs: tail -f bot.log"
echo "To stop: pkill -f quotex_bot.py"
