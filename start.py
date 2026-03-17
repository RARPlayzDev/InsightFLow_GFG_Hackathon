#!/usr/bin/env python3
"""
InsightFlow one-click launcher.
Usage: python start.py   (run from the insightflow/ project root)

What this does:
  1. Creates/validates .env (warns if GROQ_API_KEY is empty)
  2. Creates/repairs the Python virtual environment
  3. Installs backend deps with --only-binary (no compilation)
  4. Runs npm install if node_modules is absent
  5. Launches uvicorn (backend) and vite dev server (frontend) concurrently
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

# ── Path constants ────────────────────────────────────────────────

ROOT     = Path(__file__).parent.resolve()
BACKEND  = ROOT / "backend"
FRONTEND = ROOT / "frontend"
SESSIONS = ROOT / "sessions"
VENV_DIR = BACKEND / "venv"

_BIN = "Scripts" if sys.platform == "win32" else "bin"
_EXE = ".exe"   if sys.platform == "win32" else ""

PYTHON_VENV = VENV_DIR / _BIN / f"python{_EXE}"
UVICORN     = VENV_DIR / _BIN / f"uvicorn{_EXE}"


# ── Helpers ────────────────────────────────────────────────────────

def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    # shell=True required on Windows for npm/node commands
    use_shell = sys.platform == "win32"
    return subprocess.run(cmd, check=True, shell=use_shell, **kwargs)


def _step(msg: str) -> None:
    print(f"\n\033[1;34m▶ {msg}\033[0m")


def _ok(msg: str) -> None:
    print(f"\033[0;32m  ✓ {msg}\033[0m")


def _warn(msg: str) -> None:
    print(f"\033[0;33m  ⚠ {msg}\033[0m")


def _err(msg: str) -> None:
    print(f"\033[0;31m  ✗ {msg}\033[0m")


# ── 1. sessions/ directory ─────────────────────────────────────────

SESSIONS.mkdir(exist_ok=True)


# ── 2. .env file ───────────────────────────────────────────────────

env_file = ROOT / ".env"
if not env_file.exists():
    example = ROOT / ".env.example"
    if example.exists():
        shutil.copy(example, env_file)
        _warn("Created .env from .env.example — set your GROQ_API_KEY inside it.")
    else:
        env_file.write_text("GROQ_API_KEY=\nGROQ_MODEL=llama-3.3-70b-versatile\n")
        _warn(".env created — add GROQ_API_KEY=your_key_here before querying.")

# Warn if key is empty (app runs but queries will fail)
env_content = env_file.read_text()
if "GROQ_API_KEY=" in env_content and "GROQ_API_KEY=\n" in env_content:
    _warn("GROQ_API_KEY is empty in .env — AI queries will return 'unavailable'.")


# ── 3. Python virtual environment ─────────────────────────────────

_step("Python virtual environment…")

# Wipe broken venv: folder exists but uvicorn wasn't installed (previous pip failed)
if VENV_DIR.exists() and not UVICORN.exists():
    _warn("Broken venv detected — wiping and recreating…")
    shutil.rmtree(VENV_DIR)

if not VENV_DIR.exists():
    print("  Creating virtual environment…")
    # Use subprocess directly (not _run) — sys.executable is a real path, not a shell command
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)

# Upgrade pip silently
subprocess.run(
    [str(PYTHON_VENV), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
    check=True,
)

# Install requirements — --only-binary prevents source compilation on any Python version
req = BACKEND / "requirements.txt"
result = subprocess.run(
    [str(PYTHON_VENV), "-m", "pip", "install", "-r", str(req),
     "--only-binary=:all:", "--quiet"],
    capture_output=True, text=True,
)
if result.returncode != 0:
    _err("pip install failed:\n" + result.stderr)
    sys.exit(1)

_ok("Backend dependencies ready")


# ── 4. npm install ────────────────────────────────────────────────

_step("Frontend dependencies…")

nm = FRONTEND / "node_modules"
# Check for package-lock.json in project root (npm 7+ also writes node_modules/.package-lock.json)
lock_exists = (FRONTEND / "package-lock.json").exists() or (nm / ".package-lock.json").exists()

if not nm.exists() or not lock_exists:
    print("  Running npm install…")
    _run(["npm", "install", "--prefix", str(FRONTEND)])

_ok("Frontend dependencies ready")


# ── 5. Launch both servers ─────────────────────────────────────────

_step("Starting InsightFlow…")
print()
print("  Backend  →  http://127.0.0.1:8000")
print("  Frontend →  http://localhost:5173")
print()
print("  Open http://localhost:5173 in your browser")
print("  Press Ctrl+C to stop\n")


def run_backend() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    subprocess.run(
        [str(UVICORN), "main:app",
         "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=str(BACKEND),
        env=env,
    )


def run_frontend() -> None:
    _run(["npm", "run", "dev", "--prefix", str(FRONTEND)])


backend_thread = threading.Thread(target=run_backend, daemon=True)
backend_thread.start()

try:
    run_frontend()
except KeyboardInterrupt:
    print("\n\n  InsightFlow stopped.")
