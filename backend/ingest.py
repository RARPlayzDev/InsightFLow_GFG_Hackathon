"""
ingest.py
─────────────────────────────────────────────────────────
CSV → SQLite ingest pipeline.
Zero compiled dependencies — uses only Python stdlib.

Pipeline:
  1. strip_safari_wrapper()  — remove bplist/HTML wrappers (GFG dataset only)
  2. detect_encoding()       — UTF-8 → latin-1 fallback
  3. csv.DictReader()        — parse rows as dicts
  4. sanitize_column_names() — safe SQL identifiers, no duplicates
  5. _infer_sql_type()       — INTEGER / REAL / TEXT per column
  6. classify_column()       — continuous/score/measure/dimension/id/datetime/text
  7. compute_bucket_sql()    — CASE WHEN SQL for continuous columns
  8. sqlite3.executemany()   — write all rows with WAL mode
"""
from __future__ import annotations
import csv
import io
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from session_store import ColumnMeta, SchemaPayload

# ── Module-level constants ─────────────────────────────────────────

AMBIGUOUS_COLUMNS = {"product_availability_online"}

# Compiled once at module load — used in classify_column() for every column
_DATE_PAT = re.compile(
    r"^\d{4}-\d{2}-\d{2}|^\d{2}/\d{2}/\d{4}|^\d{4}/\d{2}/\d{2}"
)


# ── 1. Safari WebArchive wrapper stripping ────────────────────────

def strip_safari_wrapper(raw: bytes) -> bytes:
    """
    Strip Safari WebArchive (bplist + HTML) wrapper from CSV bytes.

    The GFG dataset is saved by Safari as a WebArchive:
      bplist header → HTML wrapper → <pre>CSV data</pre> → HTML tail

    The structure is:
      bplist00... (binary header)
      ...WebResourceData...
      <html><head>...</head><body><pre ...>age,monthly_income,...\n
      row1\nrow2\n...
      </pre></body></html>Xtext/csv (HTML tail)

    Extraction strategy (in order):
    1. Look for b">age," — the HTML <pre> closing > immediately before the
       CSV header. Start right after the >.
       Also strip any HTML tail (</pre>...) from the end.
    2. Fallback for other wrapped CSVs: find b">word," pattern.
    3. If no wrapper detected (normal CSV), return raw unchanged.

    This is the permanent fix for the bplist structure — rfind("\n") before
    "age," would land inside the binary header, not at the CSV start.
    """
    # Step 1: bplist/HTML wrapper — CSV header follows immediately after ">"
    for header_marker in (b">age,", b'>age,'):
        idx = raw.find(header_marker)
        if idx != -1:
            csv_start = idx + 1  # skip the ">"
            # Strip HTML tail: </pre></body></html>... appended after CSV data
            csv_bytes = raw[csv_start:]
            tail = csv_bytes.find(b"</")
            if tail != -1:
                csv_bytes = csv_bytes[:tail]
            return csv_bytes

    # Step 2: generic fallback — only if file looks binary/HTML-wrapped
    is_wrapped = (
        raw[:6] == b"bplist"
        or raw[:6].lower() == b"<html>"
        or b"WebResourceData" in raw[:512]
    )
    if not is_wrapped:
        return raw  # plain CSV — return unchanged

    # Find ">word," pattern (generic wrapped CSV)
    match = re.search(rb">([A-Za-z_][A-Za-z0-9_]*,)", raw)
    if match:
        csv_bytes = raw[match.start() + 1:]
        tail = csv_bytes.find(b"</")
        return csv_bytes[:tail] if tail != -1 else csv_bytes

    return raw  # give up — let csv parser raise a clear error


# ── 2. Encoding detection ─────────────────────────────────────────

def detect_encoding(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


# ── 3-4. Column name sanitisation ────────────────────────────────

def sanitize_column_names(names: List[str]) -> List[str]:
    """
    Convert arbitrary header strings to safe SQL identifiers.
    - Replaces non-alphanumeric chars with underscores
    - Lowercases
    - Deduplicates with _2 / _3 suffix
    - Prefixes col_ if name starts with a digit
    """
    seen: Dict[str, int] = {}
    result = []
    for name in names:
        safe_name = name if name is not None else "col"
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", str(safe_name).strip()).lower()
        safe = re.sub(r"_+", "_", safe).strip("_") or "col"
        if safe[0].isdigit():
            safe = "col_" + safe
        count = seen.get(safe, 0)
        seen[safe] = count + 1
        result.append(safe if count == 0 else f"{safe}_{count + 1}")
    return result


# ── 5. SQL type inference ─────────────────────────────────────────

def _infer_sql_type(values: List[str]) -> str:
    non_empty = [v for v in values if v is not None and str(v).strip()]
    if not non_empty:
        return "TEXT"
    int_pat = re.compile(r"^-?\d+$")
    float_pat = re.compile(r"^-?\d+\.\d+$")
    if all(int_pat.match(v) for v in non_empty):
        return "INTEGER"
    if all(int_pat.match(v) or float_pat.match(v) for v in non_empty):
        return "REAL"
    return "TEXT"


# ── 6. Column role classification ────────────────────────────────

def classify_column(sql_type: str, nunique: int, total: int, values: List[str]) -> str:
    """
    Map a column to one of: continuous | score | measure | dimension | id | datetime | text
    Uses the module-level _DATE_PAT constant (compiled once, not per-call).
    """
    non_empty = [v for v in values if v is not None and str(v).strip()]

    # Date check first — applies to TEXT columns that look like dates
    if non_empty and _DATE_PAT.match(non_empty[0]):
        return "datetime"

    if sql_type == "TEXT":
        return "dimension" if nunique <= 20 else "text"

    # Numeric roles by cardinality
    if nunique <= 10:
        return "score"
    if nunique <= 20:
        return "measure"
    if sql_type == "INTEGER" and nunique / max(total, 1) > 0.99:
        return "id"
    return "continuous"


# ── 7. Bucket SQL for continuous columns ─────────────────────────

def compute_bucket_sql(safe_name: str, values: List[str]) -> Optional[str]:
    """
    Build a CASE WHEN expression that buckets a continuous numeric column
    into four quartile-based ranges. Returns None if the column has no
    numeric values or all values are identical.
    """
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except (ValueError, TypeError):
            pass
    if not nums:
        return None

    mn, mx = min(nums), max(nums)
    if mx == mn:
        return None

    sorted_nums = sorted(nums)
    n = len(sorted_nums)

    def pct(p: float) -> float:
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        return sorted_nums[lo] + (idx - lo) * (sorted_nums[hi] - sorted_nums[lo])

    col = f'"{safe_name}"'
    b1 = int(mn)
    b2 = max(int(pct(0.25)), b1 + 1)
    b3 = max(int(pct(0.50)), b2 + 1)
    b4 = max(int(pct(0.75)), b3 + 1)

    return (
        f"CASE "
        f"WHEN {col} < {b2} THEN '{b1}–{b2-1}' "
        f"WHEN {col} < {b3} THEN '{b2}–{b3-1}' "
        f"WHEN {col} < {b4} THEN '{b3}–{b4-1}' "
        f"ELSE '{b4}+' END"
    )


# ── 8. Main entry point ───────────────────────────────────────────

def ingest_csv(raw: bytes, dataset_name: str, db_path: str) -> SchemaPayload:
    """
    Full pipeline: raw CSV bytes → SQLite database + SchemaPayload.
    Raises ValueError for invalid CSV, RuntimeError for DB write failures.
    """
    raw = strip_safari_wrapper(raw)
    enc = detect_encoding(raw)
    text = raw.decode(enc, errors="replace").lstrip("\ufeff")  # strip BOM

    # Normalise line endings before parsing. Windows files use \r\n;
    # some editors produce \r alone. Normalize all to \n.
    # Pass newline="" to StringIO — required by Python csv docs so quoted
    # fields containing embedded newlines parse correctly instead of raising:
    #   "new-line character seen in unquoted field"
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    reader = csv.DictReader(io.StringIO(text, newline=''))
    original_names = list(reader.fieldnames or [])
    if not original_names:
        raise ValueError("CSV has no header row")

    safe_names = sanitize_column_names(original_names)
    name_map = dict(zip(original_names, safe_names))

    def clean_value(val: str) -> Optional[str]:
        if not val:
            return None
        s = str(val).strip()
        if s.upper() in ("NULL", "NA", "N/A", "NAN", "-") or s == "":
            return None
        return s

    rows = [{name_map[k]: clean_value(v) for k, v in row.items() if k in name_map} for row in reader]
    if not rows:
        raise ValueError("CSV has no data rows")

    total = len(rows)

    # Collect per-column values for stats
    col_values: Dict[str, List[str]] = {s: [] for s in safe_names}
    for row in rows:
        for s in safe_names:
            col_values[s].append(row.get(s, ""))

    # Derive table name from dataset filename
    table_name = re.sub(r"[^a-zA-Z0-9_]", "_", dataset_name.split(".")[0])[:40] or "data"
    table_name = table_name.lower()
    if table_name[0].isdigit():
        table_name = "t_" + table_name

    # Build column metadata
    col_metas: List[ColumnMeta] = []
    col_defs: List[str] = []

    for orig, safe in zip(original_names, safe_names):
        vals = col_values[safe]
        sql_type = _infer_sql_type(vals)
        non_empty = [v for v in vals if v is not None and str(v).strip()]
        nunique = len(set(non_empty))
        role = classify_column(sql_type, nunique, total, vals)
        samples = list(dict.fromkeys(v for v in non_empty if v))[:3]
        bucket_sql = compute_bucket_sql(safe, vals) if role == "continuous" else None

        col_metas.append(ColumnMeta(
            original_name=orig,
            safe_name=safe,
            role=role,
            sql_type=sql_type,
            nunique=nunique,
            samples=samples,
            bucket_sql=bucket_sql,
            is_ambiguous=(safe in AMBIGUOUS_COLUMNS),
        ))
        col_defs.append(f'"{safe}" {sql_type}')

    has_date = any(c.role == "datetime" for c in col_metas)

    # Write to SQLite with WAL mode for concurrent read safety
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(str(db), check_same_thread=False) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.execute(f'CREATE TABLE "{table_name}" ({", ".join(col_defs)})')
            placeholders = ", ".join("?" for _ in safe_names)
            conn.executemany(
                f'INSERT INTO "{table_name}" VALUES ({placeholders})',
                [[row.get(s) for s in safe_names] for row in rows],
            )
            conn.commit()
    except sqlite3.Error as e:
        raise RuntimeError(f"Database write failed: {e}") from e

    return SchemaPayload(
        table_name=table_name,
        dataset_name=dataset_name,
        row_count=total,
        columns=col_metas,
        has_date_column=has_date,
    )
