# Setup virtual environment for ComfyUI Dependency Analyzer (Windows)
$ErrorActionPreference = "Stop"

# Find Python
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" }
      elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" }
      elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" }
      else { Write-Error "Python not found"; exit 1 }

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    & $py -m venv .venv
} else {
    Write-Host "Virtual environment already exists."
}

Write-Host "Installing dependencies..."
& .\.venv\Scripts\pip.exe install -r requirements.txt --quiet
Write-Host "Starting TUI..."
& .\.venv\Scripts\python.exe -m dep_tui
