import sys
from pathlib import Path

# Add backend to Python path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from main import app  # noqa: E402 — Vercel discovers this `app` object
