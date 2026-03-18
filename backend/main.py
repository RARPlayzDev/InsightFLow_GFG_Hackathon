

# load_dotenv is called HERE, once, before any other local imports.
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import os
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from security import limiter

MAX_PROMPT_LEN = 500
MAX_REFINE_LEN = 300
MAX_CHAT_LEN = 500

def _sanitize_text(text: str) -> str:
    if not text: return ""
    return "".join(c for c in text if "\x20" <= c <= "\x7E" or c in "\n\r\t").strip()

from ingest import ingest_csv
from query_pipeline import run_query, run_refine
from session_store import get_session, set_session, SessionData

app = FastAPI(title="InsightFlow API")
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please slow down and try again later."}
    )

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

IS_VERCEL = os.environ.get("VERCEL", "") == "1"

if IS_VERCEL:
    import tempfile
    SESSIONS_DIR = Path(tempfile.gettempdir()) / "insightflow_sessions"
else:
    SESSIONS_DIR = Path(__file__).parent.parent / "sessions"

SESSIONS_DIR.mkdir(exist_ok=True)

GFG_CSV = Path(__file__).parent.parent / "data" / "Customer_Behaviour__Online_vs_Offline_.csv"


# ── Request models ─────────────────────────────────────────────────────────────

@dataclass
class QueryRequest:
    prompt: str = ""


@dataclass
class RefineRequest:
    message: str = ""
    original_prompt: str = ""


@dataclass
class ChatRequest:
    message: str = ""
    history: list = None


# ── Helper ─────────────────────────────────────────────────────────────────────

def _get_sid(x_session_id: Optional[str]) -> str:
    if not x_session_id or not x_session_id.strip():
        raise HTTPException(status_code=400, detail="X-Session-ID header is required")
    return x_session_id.strip()


def _clean_env(key: str, default: str = "") -> str:
    """Read env var and strip surrounding quotes that dotenv can leave."""
    return os.getenv(key, default).strip().strip('"').strip("'").strip()


# ── Routes ──────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    api_key  = _clean_env("GROQ_API_KEY")
    key_ok   = bool(api_key) and len(api_key) > 20
    return {
        "status": "ok",
        "groq_key_set": key_ok,
        "groq_key_looks_valid": key_ok,
        "groq_key_prefix": (api_key[:8] + "...") if api_key else "NOT SET",
        "groq_model": _clean_env("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "gfg_dataset_exists": GFG_CSV.exists(),
        "llm_provider": "groq",
    }


@app.get("/health/summary")
def health_summary():
    from llm_providers import _get_all_keys
    keys = _get_all_keys()
    
    return {
        "api":     True,
        "keys_loaded": len(keys),
        "dataset": GFG_CSV.exists(),
    }


@app.get("/debug-llm")
def debug_llm():
    """
    Fires a minimal test call to Groq and returns the raw response.
    Open http://localhost:8000/debug-llm in your browser to diagnose issues.
    """
    import httpx as _httpx

    api_key = _clean_env("GROQ_API_KEY")
    model   = _clean_env("GROQ_MODEL", "llama-3.3-70b-versatile")

    if not api_key:
        return {"ok": False, "problem": "GROQ_API_KEY not set in .env"}

    url     = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say the word hello"}],
        "max_tokens": 10,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        r    = _httpx.post(url, json=payload, headers=headers, timeout=20.0)
        body = r.json() if "application/json" in r.headers.get("content-type", "") else {"raw": r.text[:600]}
        return {
            "ok":          r.status_code == 200,
            "http_status": r.status_code,
            "key_prefix":  api_key[:8] + "...",
            "model":       model,
            "response":    body,
        }
    except Exception as e:
        return {"ok": False, "problem": str(e)}


@app.post("/preload")
@limiter.limit("5/minute")
def preload(request: Request, x_session_id: Optional[str] = Header(None)):
    sid = _get_sid(x_session_id)

    # Return cached schema if session already loaded — avoids re-ingesting on every nav
    existing = get_session(sid)
    if existing and existing.schema:
        s = existing.schema
        return {
            "ok": True, "cached": True,
            "table_name": s.table_name, "dataset_name": s.dataset_name,
            "row_count": s.row_count, "column_count": len(s.columns),
            "has_date_column": s.has_date_column,
        }

    if not GFG_CSV.exists():
        raise HTTPException(
            status_code=404,
            detail="GFG dataset not found. Ensure data/Customer_Behaviour__Online_vs_Offline_.csv exists."
        )

    db_path = str(SESSIONS_DIR / f"{sid}.db")

    # Delete stale DB files from previous server runs.
    # Without this, WAL journal replay causes "table already exists" errors.
    for suffix in ("", "-wal", "-shm"):
        f = Path(db_path + suffix) if suffix else Path(db_path)
        if f.exists():
            try:
                f.unlink()
            except OSError:
                pass

    try:
        raw    = GFG_CSV.read_bytes()
        schema = ingest_csv(raw, GFG_CSV.name, db_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dataset ingest failed: {e}")

    set_session(sid, SessionData(schema=schema, db_path=db_path))

    return {
        "ok": True, "cached": False,
        "table_name": schema.table_name, "dataset_name": schema.dataset_name,
        "row_count": schema.row_count, "column_count": len(schema.columns),
        "has_date_column": schema.has_date_column,
    }


@app.post("/upload-csv", response_model=None)
@limiter.limit("3/minute")
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    x_session_id: Optional[str] = Header(None),
):
    sid = _get_sid(x_session_id)

    safe_filename = "".join(c for c in (file.filename or "") if c.isalnum() or c in "._-").strip()
    if not safe_filename or not safe_filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    
    file.filename = safe_filename

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    db_path = str(SESSIONS_DIR / f"{sid}.db")

    for suffix in ("", "-wal", "-shm"):
        f = Path(db_path + suffix) if suffix else Path(db_path)
        if f.exists():
            try:
                f.unlink()
            except OSError:
                pass

    try:
        schema = ingest_csv(raw, file.filename, db_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")

    set_session(sid, SessionData(schema=schema, db_path=db_path))

    return {
        "ok": True,
        "table_name": schema.table_name, "dataset_name": schema.dataset_name,
        "row_count": schema.row_count, "column_count": len(schema.columns),
        "has_date_column": schema.has_date_column,
    }


@app.get("/schema")
@limiter.limit("10/minute")
def get_schema(request: Request, x_session_id: Optional[str] = Header(None)):
    sid  = _get_sid(x_session_id)
    sess = get_session(sid)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found or expired. Reload the dataset.")

    return {
        "table_name":      sess.schema.table_name,
        "dataset_name":    sess.schema.dataset_name,
        "row_count":       sess.schema.row_count,
        "has_date_column": sess.schema.has_date_column,
        "columns": [
            {
                "safe_name":     c.safe_name,
                "original_name": c.original_name,
                "role":          c.role,
                "sql_type":      c.sql_type,
                "nunique":       c.nunique,
                "samples":       c.samples,
                "is_ambiguous":  c.is_ambiguous,
            }
            for c in sess.schema.columns
        ],
    }


@app.get("/data-preview")
@limiter.limit("10/minute")
def data_preview(request: Request, x_session_id: Optional[str] = Header(None)):
    sid  = _get_sid(x_session_id)
    sess = get_session(sid)
    if not sess or not sess.schema:
        raise HTTPException(status_code=404, detail="Session not found or expired. Reload the dataset.")

    import sqlite3
    db_path = sess.db_path
    table = sess.schema.table_name

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM `{table}` LIMIT 100")
            rows = [dict(row) for row in cursor.fetchall()]

            # Determine headers from the schema
            headers = [c.safe_name for c in sess.schema.columns]
            
            return {
                "ok": True,
                "headers": headers,
                "rows": rows
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch preview: {str(e)}")


@app.post("/auto-report")
@limiter.limit("2/minute")
def auto_report(request: Request, x_session_id: Optional[str] = Header(None)):
    sid = _get_sid(x_session_id)
    from query_pipeline import run_auto_report
    result = run_auto_report(sid)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/query")
@limiter.limit("10/minute")
def query(request: Request, req: QueryRequest, x_session_id: Optional[str] = Header(None)):
    sid = _get_sid(x_session_id)
    sanitized_prompt = _sanitize_text(req.prompt)
    if not sanitized_prompt:
        raise HTTPException(status_code=400, detail="prompt must not be empty")
    if len(sanitized_prompt) > MAX_PROMPT_LEN:
        raise HTTPException(status_code=400, detail=f"Query too long (max {MAX_PROMPT_LEN} chars)")

    result = run_query(sanitized_prompt, sid)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/refine")
@limiter.limit("10/minute")
def refine(request: Request, req: RefineRequest, x_session_id: Optional[str] = Header(None)):
    sid = _get_sid(x_session_id)
    sanitized_msg = _sanitize_text(req.message)
    if not sanitized_msg:
        raise HTTPException(status_code=400, detail="message must not be empty")
    if len(sanitized_msg) > MAX_REFINE_LEN:
        raise HTTPException(status_code=400, detail=f"Query too long (max {MAX_REFINE_LEN} chars)")

    result = run_refine(sanitized_msg, sid, _sanitize_text(req.original_prompt) or "")
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/chat")
@limiter.limit("5/minute")
def chat(request: Request, req: ChatRequest, x_session_id: Optional[str] = Header(None)):
    sid = _get_sid(x_session_id)
    sanitized_msg = _sanitize_text(req.message)
    if not sanitized_msg:
        raise HTTPException(status_code=400, detail="message must not be empty")
    if len(sanitized_msg) > MAX_CHAT_LEN:
        raise HTTPException(status_code=400, detail=f"Message too long (max {MAX_CHAT_LEN} chars)")

    from query_pipeline import run_chat
    from session_store import get_session, set_session
    
    sess = get_session(sid)
    if sess:
        sess.chat_history.append({"role": "user", "content": sanitized_msg})
        # Pass all history except the current message just appended
        result = run_chat(sanitized_msg, sess.chat_history[:-1], sid)
        if "error" not in result:
            sess.chat_history.append({"role": "assistant", "content": result.get("response", "")})
            set_session(sid, sess)
        else:
            sess.chat_history.pop()
    else:
        result = run_chat(sanitized_msg, req.history or [], sid)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.delete("/history")
def clear_history(x_session_id: Optional[str] = Header(None)):
    """Clear query history for this session but keep the dataset loaded."""
    sid  = _get_sid(x_session_id)
    sess = get_session(sid)
    if sess:
        sess.history = []
        set_session(sid, sess)
    return {"ok": True}


@app.post("/overview")
@limiter.limit("5/minute")
def dataset_overview(request: Request, x_session_id: Optional[str] = Header(None)):
    """
    Generate an AI overview of the loaded dataset.
    Called once after dataset loads. Returns a plain-English summary
    plus a structured breakdown of column groups.
    """
    from query_pipeline import call_llm
    from schema_context import build_schema_context

    sid  = _get_sid(x_session_id)
    sess = get_session(sid)
    if not sess or not sess.schema:
        raise HTTPException(status_code=404, detail="No dataset loaded.")

    schema = sess.schema
    ctx    = build_schema_context(schema)

    prompt = f"""You are a data analyst. A dataset has just been loaded. Give a concise overview.

SCHEMA:
{ctx}

Respond with ONLY valid JSON — no markdown, no backticks:
{{
  "summary": "2-3 sentence plain-English description of what this dataset contains, who the subjects are, and what questions it can answer. Write for someone unfamiliar with the data.",
  "expert_note": "1-2 sentences pointing out the most analytically interesting structure — e.g. skewed distributions, notable correlations expected, any caveats about ambiguous columns. Write for someone who knows data.",
  "column_groups": [
    {{"group": "Group name", "columns": ["col1", "col2"], "description": "Short description"}}
  ],
  "suggested_questions": [
    "Question 1",
    "Question 2",
    "Question 3"
  ]
}}

Rules:
- column_groups: 3-5 logical groups (demographics, behaviour, spending, psychographic, etc.)
- suggested_questions: exactly 3, specific to this dataset's columns, answerable with the data
- Use safe_names for columns in column_groups
- Keep summary under 60 words
- Keep expert_note under 40 words
"""

    result = call_llm(prompt)

    # Validate — if LLM returned a cannot_answer fallback, return a default
    if result.get("cannot_answer"):
        return {
            "summary": f"Dataset with {schema.row_count:,} rows and {len(schema.columns)} columns.",
            "expert_note": "Load the dataset and explore the columns to understand the structure.",
            "column_groups": [],
            "suggested_questions": [],
        }

    return {
        "summary":            result.get("summary", ""),
        "expert_note":        result.get("expert_note", ""),
        "column_groups":      result.get("column_groups", []),
        "suggested_questions": result.get("suggested_questions", []),
    }



@app.get("/history")
def history(x_session_id: Optional[str] = Header(None)):
    sid  = _get_sid(x_session_id)
    sess = get_session(sid)
    if not sess:
        return {"expired": True, "items": []}

    return {
        "expired": False,
        "items": [
            {
                "prompt":        r.prompt,
                "timestamp":     r.timestamp,
                "chart_specs":   r.chart_specs,
                "kpi_specs":     r.kpi_specs,
                "insight":       r.insight,
                "cannot_answer": r.cannot_answer,
                "reason":        r.reason,
            }
            for r in sess.history
        ],
    }