#!/bin/bash
# Neural Nomads - Auto-start all autonomous processes
# This script is called by LaunchAgent on login

cd /Users/danielzimon/OpenClaw
VENV="/Users/danielzimon/OpenClaw/venv/bin/python3"
LOG_DIR="/Users/danielzimon/OpenClaw/logs"

# Prevent sleep
caffeinate -d -i -s &

# Start orchestrator (if not already running)
if ! pgrep -f "orchestrator.py" > /dev/null; then
    nohup $VENV orchestrator.py > /dev/null 2>&1 &
    echo "$(date) Orchestrator started (PID $!)" >> "$LOG_DIR/startup.log"
fi

# Start design loop (if not already running)
if ! pgrep -f "run_design_cycle.py" > /dev/null; then
    nohup $VENV agents/run_design_cycle.py > /dev/null 2>&1 &
    echo "$(date) Design loop started (PID $!)" >> "$LOG_DIR/startup.log"
fi

# Start Telegram bot (if not already running)
if ! pgrep -f "telegram_bot.py" > /dev/null; then
    export TELEGRAM_BOT_TOKEN="8736769933:AAHPJyZdUldrsvYcOjWQaz6olzcHKqiLRD4"
    export TELEGRAM_CHAT_ID="6703967543"
    nohup $VENV agents/telegram_bot.py > "$LOG_DIR/telegram_bot.log" 2>&1 &
    echo "$(date) Telegram bot started (PID $!)" >> "$LOG_DIR/startup.log"
fi

# Start dashboard (if not already running)
if ! pgrep -f "dashboard/server.py" > /dev/null; then
    nohup $VENV dashboard/server.py > "$LOG_DIR/dashboard.log" 2>&1 &
    echo "$(date) Dashboard started (PID $!) at http://localhost:8888" >> "$LOG_DIR/startup.log"
fi

echo "$(date) All systems online." >> "$LOG_DIR/startup.log"
