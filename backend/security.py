"""
security.py
─────────────────────────────────────────────────────────
Rate limiting and security utilities for the FastAPI app.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
