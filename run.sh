#!/usr/bin/env bash
# Setup virtual environment for ComfyUI Dependency Analyzer (macOS/Linux)
set -e

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

echo "Installing dependencies..."
.venv/bin/pip install -r requirements.txt --quiet
echo "Starting TUI..."
.venv/bin/python -m dep_tui
