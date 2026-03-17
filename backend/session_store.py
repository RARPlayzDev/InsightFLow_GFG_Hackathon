"""
session_store.py
─────────────────────────────────────────────────────────
In-memory session store with 30-minute TTL eviction.
Each session maps a browser session-ID to a loaded SQLite
database path + its schema metadata + query history.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Session lifetime ───────────────────────────────────────────────
SESSION_TTL = 1800  # 30 minutes of inactivity


# ── Schema / column metadata (populated by ingest.py) ─────────────

@dataclass
class ColumnMeta:
    original_name: str
    safe_name: str
    role: str           # continuous | score | measure | dimension | id | datetime | text
    sql_type: str       # INTEGER | REAL | TEXT
    nunique: int
    samples: List[str]
    bucket_sql: Optional[str] = None   # CASE WHEN … for continuous columns
    is_ambiguous: bool = False


@dataclass
class SchemaPayload:
    table_name: str
    dataset_name: str
    row_count: int
    columns: List[ColumnMeta]
    has_date_column: bool = False


# ── Per-query records ──────────────────────────────────────────────

@dataclass
class ChartRecord:
    """Full chart data stored for the refine prompt (uses rows[:3] for context)."""
    title: str
    sql: str
    chart_type: str
    x_col: str
    y_cols: List[str]
    color_col: Optional[str]
    note: str
    rows: List[Dict[str, Any]]
    warning: Optional[str] = None
    correlation_note: Optional[str] = None


@dataclass
class QueryRecord:
    """Lightweight record stored in history — specs only, no row data."""
    prompt: str
    timestamp: float
    chart_specs: List[Dict]   # {title, type} per chart
    kpi_specs: List[Dict]     # {label, format} per KPI
    insight: str
    cannot_answer: bool = False
    reason: str = ""


# ── Session container ──────────────────────────────────────────────

@dataclass
class SessionData:
    schema: SchemaPayload
    db_path: str
    last_charts: List[ChartRecord] = field(default_factory=list)
    last_prompt: str = ""
    history: List[QueryRecord] = field(default_factory=list)
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


# ── Store + public API ─────────────────────────────────────────────

_sessions: Dict[str, SessionData] = {}


def get_session(session_id: str) -> Optional[SessionData]:
    _evict_expired()
    sess = _sessions.get(session_id)
    if sess:
        sess.last_active = time.time()
    return sess


def set_session(session_id: str, data: SessionData) -> None:
    _evict_expired()
    _sessions[session_id] = data


def _evict_expired() -> None:
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s.last_active > SESSION_TTL]
    for sid in expired:
        del _sessions[sid]
