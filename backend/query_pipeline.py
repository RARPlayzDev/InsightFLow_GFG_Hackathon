"""
query_pipeline.py
???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
Two-stage LLM pipeline for reliable chart generation.

STAGE 1 ??? SQL Generation (narrow, verifiable)
  Input:  schema context + user question
  Output: list of SQL queries + titles + KPI SQLs
  The LLM only writes SQL ??? no chart types, no column mapping.
  SQL is immediately executed; failures are caught with real error messages.

STAGE 2 ??? Visualisation Mapping (grounded in real data)
  Input:  executed result rows + column names (REAL, not predicted)
  Output: chart type, x_col, y_cols ??? derived from actual data shape
  The LLM cannot hallucinate columns that don't exist in the result.
  Insight is written with real values injected into the prompt.

This eliminates the entire class of x_col/y_col mismatch errors that
plagued the single-pass approach, where the LLM had to predict what
columns the SQL would return before executing it.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from processor_v2 import post_process_chart, coerce_kpi_value
from schema_context import build_schema_context, get_valid_aliases
from session_store import ChartRecord, QueryRecord, SchemaPayload, get_session, set_session

BLOCKED_SQL = {"DROP", "INSERT", "UPDATE", "DELETE", "ATTACH", "PRAGMA", "SQLITE_MASTER"}

TIME_TREND_PHRASES = [
    "over time", "trend", "month over month", "year over year",
    "quarterly", "yearly", "annual", "historical", "growth rate",
    "over the past", "last month", "last year", "last quarter",
    "this quarter", "year-on-year",
]

_FALLBACK_UNAVAILABLE = {
    "cannot_answer": True,
    "reason": "AI service is temporarily unavailable. Please try again.",
    "charts": [], "kpis": [],
    "insight": "Could not generate insights ??? AI did not respond.",
}
_FALLBACK_PARSE = {
    "cannot_answer": True,
    "reason": "AI returned an unexpected format. Please try again.",
    "charts": [], "kpis": [],
    "insight": "Could not parse AI response.",
}


def _unavailable(reason: Optional[str] = None) -> Dict:
    d = copy.deepcopy(_FALLBACK_UNAVAILABLE)
    if reason:
        d["reason"] = reason
    return d


def _parse_error() -> Dict:
    return copy.deepcopy(_FALLBACK_PARSE)


# ?????? SQL Validation ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

def validate_sql(sql: str, table_name: str) -> None:
    stripped = sql.strip().lstrip("-").strip()
    upper = stripped.upper()
    if not upper.startswith("SELECT"):
        raise ValueError(f"SQL must start with SELECT, got: {stripped[:40]!r}")
    for kw in BLOCKED_SQL:
        if re.search(r"\b" + kw + r"\b", upper):
            raise ValueError(f"Blocked SQL keyword: {kw}")
    sql_lower = sql.lower()
    tbl = table_name.lower()
    quoted   = (f'"{tbl}"' in sql_lower) or (f"`{tbl}`" in sql_lower)
    unquoted = bool(re.search(r"(?<![\"'`\w])" + re.escape(tbl) + r"(?![\"'`\w])", sql_lower))
    if not (quoted or unquoted):
        raise ValueError(f"SQL does not reference table '{table_name}'.")


# ?????? SQL Execution ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

def _db_uri(db_path: str) -> str:
    posix = Path(db_path).resolve().as_posix()
    if posix.startswith("/"):
        return f"file://{posix}?mode=ro"
    return f"file:///{posix}?mode=ro"


def execute_sql(sql: str, db_path: str) -> List[Dict[str, Any]]:
    uri = _db_uri(db_path)
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql).fetchall()]
    except sqlite3.OperationalError as e:
        raise RuntimeError(f"SQL error: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Query execution failed: {e}") from e


# ?????? JSON extraction ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

def extract_json(text: str) -> Dict:
    text = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`").strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found. Preview: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse failed: {e}") from e


# ?????? LLM call with key rotation + response cache ????????????????????????????????????????????????????????????????????????????????????????????????

from llm_providers import call_llm_ladder as call_llm

# ?????? STAGE 1: SQL generation ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

def _prompt_stage1(schema_context: str, user_prompt: str, table_name: str,
                   error_feedback: str = "", last_contexts: list = None) -> str:
    error_section = ""
    if error_feedback:
        error_section = f"""
??? PREVIOUS ATTEMPT FAILED ??? FIX THIS:
{error_feedback}
Write corrected SQL that avoids this error.

"""

    context_section = ""
    if last_contexts:
        context_section = "??????????????????????????????????????????????????????????????????????????????????????????????????????????????????\nPREVIOUS QUERIES CONTEXT\nUse this to resolve 'same as before' or 'now show' references.\n??????????????????????????????????????????????????????????????????????????????????????????????????????????????????\n"
        for i, ctx in enumerate(last_contexts, 1):
            context_section += f"Q{i}: {ctx['prompt']}\nSQL: {ctx['sql']}\nCols: {', '.join(ctx['columns'])}\n\n"

    return f"""You are a SQL expert writing queries for SQLite.
YOUR ONLY JOB: write correct SQL. Do not decide chart types.

{schema_context}

{context_section}
QUESTION: {user_prompt}
{error_section}
??????????????????????????????????????????????????????????????????????????????????????????????????????????????????
SQL RULES
??????????????????????????????????????????????????????????????????????????????????????????????????????????????????

1. SELECT only. Never DROP, INSERT, UPDATE, DELETE, ATTACH, PRAGMA.
2. Table name: {table_name} ??? no other tables exist.
3. Column names: use ONLY safe_names from the schema above. NEVER invent names.
4. Quote every column with double quotes: "age", "gender", "city_tier"
5. Always end with ORDER BY on the main grouping column.

??????????????????????????????????????????????????????????????????????????????????????????????????????????????????
PATTERN RULES WITH EXAMPLES
??????????????????????????????????????????????????????????????????????????????????????????????????????????????????

PATTERN A ??? Distribution of a dimension column:
  "Show customer distribution by shopping_preference"
  ??? SELECT "shopping_preference", COUNT(*) AS "count"
    FROM {table_name} GROUP BY "shopping_preference" ORDER BY "count" DESC

PATTERN B ??? Distribution by TWO dimensions (most important pattern):
  "Show distribution by shopping_preference and city_tier"
  ??? SELECT "shopping_preference", "city_tier", COUNT(*) AS "count"
    FROM {table_name} GROUP BY "shopping_preference", "city_tier"
    ORDER BY "shopping_preference", "city_tier"
  CRITICAL: SELECT all grouping columns. GROUP BY ALL selected dimensions.

PATTERN C ??? Continuous column bucketed (look for bucket_sql in schema):
  "Show age distribution"
  ??? SELECT CASE WHEN "age" < 33 THEN '18-32' WHEN "age" < 48 THEN '33-47'
              WHEN "age" < 64 THEN '48-63' ELSE '64+' END AS "age_group",
           COUNT(*) AS "count"
    FROM {table_name} GROUP BY "age_group" ORDER BY "age_group"
  CRITICAL: Use the exact bucket_sql from schema. Alias MUST match alias shown in schema.

PATTERN D ??? Continuous column bucketed + grouped by dimension:
  "Show age distribution by shopping_preference"
  ??? SELECT CASE WHEN "age" < 33 THEN '18-32' ... END AS "age_group",
           "shopping_preference", COUNT(*) AS "count"
    FROM {table_name}
    GROUP BY "age_group", "shopping_preference"
    ORDER BY "age_group", "shopping_preference"
  CRITICAL: Include BOTH the alias AND the dimension in SELECT and GROUP BY.

PATTERN E ??? Average of a measure/score column by dimension:
  "Compare brand loyalty scores across shopping preferences"
  ??? SELECT "shopping_preference", AVG("brand_loyalty_score") AS "avg_brand_loyalty"
    FROM {table_name} GROUP BY "shopping_preference"
    ORDER BY "avg_brand_loyalty" DESC
  CRITICAL: score/measure columns ??? AVG(), not COUNT(). Never GROUP BY a score column.

PATTERN F ??? Multiple averages by dimension:
  "Compare online vs store spending by gender"
  ??? SELECT "gender",
           AVG("avg_online_spend") AS "avg_online_spend",
           AVG("avg_store_spend") AS "avg_store_spend"
    FROM {table_name} GROUP BY "gender" ORDER BY "gender"

PATTERN G ??? Average by TWO dimensions:
  "Compare online spending by gender and city_tier"
  ??? SELECT "gender", "city_tier", AVG("avg_online_spend") AS "avg_online_spend"
    FROM {table_name} GROUP BY "gender", "city_tier"
    ORDER BY "gender", "city_tier"

PATTERN H ??? KPI (single scalar):
  ??? SELECT COUNT(*) AS "total_customers" FROM {table_name}
  ??? SELECT AVG("avg_online_spend") AS "avg_spend" FROM {table_name}
  CRITICAL: KPI SQL must return EXACTLY ONE ROW with ONE VALUE.

??????????????????????????????????????????????????????????????????????????????????????????????????????????????????
RESPOND WITH ONLY THIS JSON:
??????????????????????????????????????????????????????????????????????????????????????????????????????????????????

{{
  "cannot_answer": false,
  "clarification_needed": false,
  "clarification_prompt": "",
  "reason": "",
  "charts": [
    {{
      "title": "Short descriptive title",
      "sql": "SELECT ... FROM {table_name} ..."
    }}
  ],
  "kpis": [
    {{
      "label": "Short label (3-5 words)",
      "sql": "SELECT COUNT(*) FROM {table_name}",
      "format": "number|currency|percentage|text"
    }}
  ]
}}

Limits: 1-3 chart SQLs, 2-4 KPI SQLs.

If the question CANNOT be answered (asks about time trends with no date column, asks about columns that don't exist):
{{"cannot_answer": true, "reason": "clear explanation", "charts": [], "kpis": []}}

If the question is TOO AMBIGUOUS and you must ask the user (e.g. "show spending" with multiple completely different spending columns):
{{"clarification_needed": true, "clarification_prompt": "Did you mean online spending or store spending?", "charts": [], "kpis": []}}
"""


# ?????? STAGE 2: Deterministic visualisation mapping ??????????????????????????????????????????????????????????????????????????????????????????
#
# Previously this was an LLM call. It is now fully deterministic.
# The result column shape tells us everything we need to pick a chart type:
#   - column types (text vs numeric)
#   - column count
#   - row count
#   - whether text values look like ordinal buckets (ranges, sequences)
#
# This eliminates an entire class of failures where the LLM invented column
# names, returned wrong types, or consumed an extra API call per chart.
# The post-processor still runs afterwards and applies its 8 correction rules
# (pie???bar dominance check, pivot for grouped_bar, Pearson r, etc.)

def _is_numeric_col(col: str, rows: List[Dict]) -> bool:
    """True if the column holds numeric values in the result rows."""
    vals = [r.get(col) for r in rows[:20] if r.get(col) is not None]
    if not vals:
        return False
    try:
        [float(v) for v in vals]
        return True
    except (TypeError, ValueError):
        return False


def _is_ordinal_text(col: str, rows: List[Dict]) -> bool:
    """
    True if the text column holds ordinal/sequential labels that benefit
    from a line chart over a bar chart.
    Examples that ARE ordinal: "18-32", "33-47", "64+", "Tier 1", "1", "2"
    Examples that are NOT: "Mumbai-MH", "sub-category", "yes-no"

    Rules:
    - Range pattern: ALL values match "number-number" or end with "+"
      (not just any value containing a hyphen)
    - Tier pattern: ALL values start with "Tier " (case-insensitive)
    - Pure digit sequence: ALL values are bare integers
    At least 80% of non-null values must match the pattern.
    """
    vals = [str(r.get(col, "")) for r in rows if r.get(col) is not None]
    if len(vals) < 2:
        return False

    import re as _re
    range_pat = _re.compile(r'^\d+[\-???]\d+$|^\d+\+$')
    tier_pat  = _re.compile(r'^tier\s+\d+$', _re.IGNORECASE)
    digit_pat = _re.compile(r'^\d+$')

    threshold = 0.8
    n = len(vals)

    if sum(1 for v in vals if range_pat.match(v.strip())) / n >= threshold:
        return True
    if sum(1 for v in vals if tier_pat.match(v.strip())) / n >= threshold:
        return True
    if sum(1 for v in vals if digit_pat.match(v.strip())) / n >= threshold:
        return True

    return False


def _compatible_numeric_cols(cols: List[str], rows: List[Dict]) -> List[str]:
    """
    When multiple numeric columns exist, return only those on compatible scales.
    Strategy: take the column with the highest median as the reference.
    Reject any column whose median is >1000x smaller than the reference
    (e.g. avg_delivery_days=3 vs avg_online_spend=60000 ??? ratio 20000x,
     avg_score=6 vs avg_spend=55000 ??? ratio 9166x).
    This prevents meaningless charts where one series is invisible.
    Max 3 y_cols returned ??? more than 3 series is unreadable.

    NOTE: scale check runs regardless of how many columns are passed ???
    even 2 columns can be on incompatible scales.
    """
    if len(cols) == 1:
        return cols

    def median_val(col):
        vals = []
        for r in rows:
            v = r.get(col)
            if v is not None:
                try: vals.append(abs(float(v)))
                except: pass
        if not vals: return 0
        vals.sort()
        return vals[len(vals) // 2]

    medians    = {c: median_val(c) for c in cols}
    max_med    = max(medians.values()) or 1
    compatible = [c for c in cols if max_med / max(medians[c], 0.001) <= 1000]

    # If filtering removed everything (shouldn't happen but be safe), return top 1
    if not compatible:
        compatible = [sorted(cols, key=lambda c: medians[c], reverse=True)[0]]

    # Sort by median descending, cap at 3
    compatible.sort(key=lambda c: medians[c], reverse=True)
    return compatible[:3]


def infer_viz(rows: List[Dict]) -> Dict:
    """
    Deterministically infer chart type and column mapping from result shape.
    Called with the ACTUAL rows returned by SQLite ??? never guesses.

    Decision tree:
      2 text + 1 numeric  ??? grouped_bar (long form, color_col = text[1])
      1 text + 2+ numeric ??? grouped_bar (wide form, compatible scales only)
      0 text + 2 numeric  ??? scatter
      1 text + 1 numeric, ordinal x ??? line
      1 text + 1 numeric, ???8 rows  ??? pie  (post-processor corrects if dominant)
      1 text + 1 numeric, >8 rows  ??? bar
      fallback            ??? bar (first col x, numeric cols y)
    """
    if not rows:
        return {"type": "bar", "x_col": "", "y_cols": [], "color_col": None}

    cols    = list(rows[0].keys())
    n_rows  = len(rows)
    t_cols  = [c for c in cols if not _is_numeric_col(c, rows)]
    n_cols  = [c for c in cols if _is_numeric_col(c, rows)]

    # 2 text + 1 numeric ??? grouped_bar long form (pivot happens in post-processor)
    if len(t_cols) == 2 and len(n_cols) == 1:
        return {"type": "grouped_bar", "x_col": t_cols[0],
                "y_cols": n_cols, "color_col": t_cols[1]}

    # 1 text + 2+ numeric ??? grouped_bar wide form (compatible scales only)
    if len(t_cols) == 1 and len(n_cols) >= 2:
        safe_y = _compatible_numeric_cols(n_cols, rows)
        return {"type": "grouped_bar", "x_col": t_cols[0],
                "y_cols": safe_y, "color_col": None}

    # 2 numeric only ??? scatter
    if len(t_cols) == 0 and len(n_cols) == 2:
        return {"type": "scatter", "x_col": n_cols[0],
                "y_cols": [n_cols[1]], "color_col": None}

    # 1 text + 1 numeric
    if len(t_cols) == 1 and len(n_cols) == 1:
        if _is_ordinal_text(t_cols[0], rows):
            return {"type": "line", "x_col": t_cols[0],
                    "y_cols": n_cols, "color_col": None}
        if n_rows <= 8:
            return {"type": "pie", "x_col": t_cols[0],
                    "y_cols": n_cols, "color_col": None}
        return {"type": "bar", "x_col": t_cols[0],
                "y_cols": n_cols, "color_col": None}

    # Fallback: first col x, any numeric cols as y
    if cols:
        x = cols[0]
        y = [c for c in cols[1:] if _is_numeric_col(c, rows)]
        if not y and len(cols) > 1:
            y = [cols[1]]
        return {"type": "bar", "x_col": x, "y_cols": y, "color_col": None}

    return {"type": "bar", "x_col": "", "y_cols": [], "color_col": None}


def _summarise_rows(rows: List[Dict], max_rows: int = 15) -> str:
    """
    Compact result summary for insight generation prompt.
    Sorts by the largest numeric column descending so the LLM sees
    the dominant values first ??? prevents wrong conclusions from
    alphabetically-first rows (e.g. 'Hybrid' before 'Store').
    """
    if not rows:
        return "[] (empty result)"
    cols = list(rows[0].keys())

    # Find the primary numeric column to sort by
    sort_col = None
    for c in reversed(cols):  # prefer rightmost (usually the measure)
        try:
            vals = [float(r[c]) for r in rows if r.get(c) is not None]
            if vals:
                sort_col = c
                break
        except (TypeError, ValueError):
            pass

    sorted_rows = rows
    if sort_col:
        try:
            sorted_rows = sorted(rows, key=lambda r: float(r.get(sort_col) or 0), reverse=True)
        except Exception:
            sorted_rows = rows

    sample = sorted_rows[:max_rows]
    lines  = [f"columns: {cols}", f"total rows: {len(rows)}", "rows (sorted by {sort_col} desc):".format(sort_col=sort_col or 'original order')]
    for r in sample:
        lines.append(f"  {dict(r)}")
    if len(rows) > max_rows:
        lines.append(f"  ??? ({len(rows) - max_rows} more rows)")
    return "\n".join(lines)



def _prompt_insight(user_prompt: str, charts_summary: str, schema_columns: List[str] = None) -> str:
    cols_ctx = f"\nRelevant columns: {', '.join(schema_columns[:15])}" if schema_columns else ""
    return f"""Analyze the business results shown below.
    
    ORIGINAL QUESTION: {user_prompt}
    {cols_ctx}
    
    RESULTS:
    {charts_summary}
    
    Please provide:
    1. A bulleted 'insight' (3-5 stars *). 
    2. A list of 'brief_insights' (3-5 concise, ONE-LINE business observations).
    3. Exactly 3 'suggestions' (short follow-up questions the user might ask next).
    4. A 'dataset_overview' object ONLY if this is the first analysis of this data:
       {{"summary": "2-3 sentences", "expert_note": "1-2 sentences"}}
    
    Respond with ONLY this JSON:
    {{
      "insight": "bulleted list here",
      "brief_insights": ["one-liner 1", "one-liner 2"],
      "suggestions": ["Q1", "Q2", "Q3"],
      "dataset_overview": {{"summary": "...", "expert_note": "..."}}
    }}
    """


# ?????? Two-stage pipeline core ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

def _run_two_stage(
    prompt: str,
    schema: SchemaPayload,
    db_path: str,
    schema_context: str,
    last_contexts: list = None
) -> Dict:
    """
    Execute the two-stage pipeline and return the assembled result dict.
    Falls back gracefully at each stage ??? a failed Stage 2 still shows
    the chart with inferred metadata rather than nothing.
    """
    # ?????? Safe initialisers ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    insight, brief_insights, suggestions, dataset_overview = "", [], [], None
    insight_resp = {}
    chart_records = []
    chart_responses = []
    results_for_insight = []

    # ?????? Stage 1: Generate SQL ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    stage1 = call_llm(_prompt_stage1(schema_context, prompt, schema.table_name, last_contexts=last_contexts))

    if stage1.get("cannot_answer"):
        return {
            "cannot_answer": True,
            "reason": stage1.get("reason", ""),
            "charts": [], "kpis": [], "insight": "", "suggestions": [],
        }

    if stage1.get("clarification_needed"):
        return {
            "cannot_answer": False,
            "clarification_needed": True,
            "clarification_prompt": stage1.get("clarification_prompt", "Please clarify your request."),
            "charts": [], "kpis": [], "insight": "", "suggestions": [],
        }

    chart_specs = stage1.get("charts", [])
    kpi_specs   = stage1.get("kpis", [])

    if not chart_specs and not kpi_specs:
        return {
            "cannot_answer": True,
            "reason": "AI did not generate any queries for this question. Try rephrasing.",
            "charts": [], "kpis": [], "insight": "", "suggestions": [],
        }

    # ?????? Execute SQLs and run Stage 2 per chart ???????????????????????????????????????????????????????????????
    chart_records   = []
    chart_responses = []
    results_for_insight = []

    for spec in chart_specs:
        sql   = spec.get("sql", "").strip()
        title = spec.get("title", "Untitled")

        if not sql:
            continue

        # ?????? Validate SQL ?????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
        try:
            validate_sql(sql, schema.table_name)
        except ValueError as e:
            # Retry Stage 1 once with the validation error fed back
            print(f"[SQL] Validation failed for '{title}': {e} ??? retrying Stage 1", file=sys.stderr)
            retry = call_llm(_prompt_stage1(schema_context, prompt, schema.table_name,
                                            error_feedback=f"SQL validation error: {e}\nBad SQL was: {sql}"))
            retry_specs = retry.get("charts", [])
            if retry_specs:
                sql = retry_specs[0].get("sql", "").strip()
                try:
                    validate_sql(sql, schema.table_name)
                except ValueError as e2:
                    chart_responses.append({
                        "title": title, "type": "bar", "x_col": "", "y_cols": [],
                        "color_col": None, "note": "", "sql": sql, "rows": [],
                        "warning": f"SQL error (after retry): {e2}", "_type_corrected": False,
                    })
                    continue
            else:
                chart_responses.append({
                    "title": title, "type": "bar", "x_col": "", "y_cols": [],
                    "color_col": None, "note": "", "sql": sql, "rows": [],
                    "warning": f"SQL validation error: {e}", "_type_corrected": False,
                })
                continue

        # ?????? Execute SQL ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
        try:
            rows = execute_sql(sql, db_path)
        except RuntimeError as e:
            # Retry Stage 1 once with the execution error fed back
            print(f"[SQL] Execution failed for '{title}': {e} ??? retrying Stage 1", file=sys.stderr)
            retry = call_llm(_prompt_stage1(schema_context, prompt, schema.table_name,
                                            error_feedback=f"SQL execution error: {e}\nBad SQL was: {sql}"))
            retry_specs = retry.get("charts", [])
            if retry_specs:
                sql = retry_specs[0].get("sql", "").strip()
                try:
                    validate_sql(sql, schema.table_name)
                    rows = execute_sql(sql, db_path)
                except Exception as e2:
                    chart_responses.append({
                        "title": title, "type": "bar", "x_col": "", "y_cols": [],
                        "color_col": None, "note": "", "sql": sql, "rows": [],
                        "warning": f"SQL error (after retry): {e2}", "_type_corrected": False,
                    })
                    continue
            else:
                chart_responses.append({
                    "title": title, "type": "bar", "x_col": "", "y_cols": [],
                    "color_col": None, "note": "", "sql": sql, "rows": [],
                    "warning": str(e), "_type_corrected": False,
                })
                continue

        if not rows:
            chart_responses.append({
                "title": title, "type": "bar", "x_col": "", "y_cols": [],
                "color_col": None, "note": "", "sql": sql, "rows": [],
                "warning": "no_matching_data", "_type_corrected": False,
            })
            continue

        results_for_insight.append(f"{title}:\n{_summarise_rows(rows, 15)}")

        # Store raw row count BEFORE post-processing (pivot changes row count)
        raw_row_count = len(rows)

        # ?????? Stage 2: Deterministic visualisation mapping ?????????????????????????????????
        # No LLM call ??? infer chart type and axes from actual result shape.
        # This eliminates the entire class of "wrong x_col" and "invalid column"
        # errors that occurred when the LLM was deciding visualisation.
        viz = infer_viz(rows)

        # Assemble spec and post-process
        full_spec = {
            "title":     title,
            "sql":       sql,
            "type":      viz["type"],
            "x_col":     viz["x_col"],
            "y_cols":    viz["y_cols"],
            "color_col": viz["color_col"],
            "note":      "",
        }

        enriched = post_process_chart(dict(full_spec), rows)

        chart_records.append(ChartRecord(
            title=enriched.get("title", ""), sql=sql,
            chart_type=enriched.get("type", "bar"),
            x_col=enriched.get("x_col", ""), y_cols=enriched.get("y_cols", []),
            color_col=enriched.get("color_col"), note=enriched.get("note", ""),
            rows=enriched.get("rows", []), warning=enriched.get("warning"),
            correlation_note=enriched.get("correlation_note"),
        ))
        chart_responses.append({
            "title":            enriched.get("title", ""),
            "type":             enriched.get("type", "bar"),
            "x_col":            enriched.get("x_col", ""),
            "y_cols":           enriched.get("y_cols", []),
            "color_col":        enriched.get("color_col"),
            "note":             enriched.get("note", ""),
            "sql":              sql,
            "rows":             enriched.get("rows", []),
            "raw_row_count":    raw_row_count,
            "warning":          enriched.get("warning"),
            "correlation_note": enriched.get("correlation_note"),
            "_type_corrected":  enriched.get("_type_corrected", False),
        })

    # ?????? KPI processing (unchanged from before) ???????????????????????????????????????????????????????????????
    kpi_responses = []
    for kspec in kpi_specs:
        sql   = kspec.get("sql", "").strip()
        fmt   = kspec.get("format", "number")
        label = kspec.get("label", "")
        value = None
        if sql:
            try:
                validate_sql(sql, schema.table_name)
                kpi_rows = execute_sql(sql, db_path)
                value    = coerce_kpi_value(kpi_rows, fmt)
            except Exception as e:
                print(f"[SQL] KPI error '{label}': {e}", file=sys.stderr)
        kpi_responses.append({"label": label, "value": value, "format": fmt, "sql": sql})

    # ?????? Insight generation with real data ??????????????????????????????????????????????????????????????????????????????
    insight = ""
    brief_insights = stage1.get("brief_insights", [])
    suggestions = stage1.get("suggestions", [])
    
    if results_for_insight and chart_responses:
        try:
            # Pass schema columns to help the LLM suggest relevant follow-ups
            cols = [c.safe_name for c in schema.columns]
            insight_resp = call_llm(_prompt_insight(prompt, "\n\n".join(results_for_insight), cols))
            
            if isinstance(insight_resp, dict):
                insight = insight_resp.get("insight", "")
                if insight_resp.get("brief_insights"):
                    brief_insights = insight_resp.get("brief_insights")
                if insight_resp.get("suggestions"):
                    suggestions = insight_resp.get("suggestions")
                dataset_overview = insight_resp.get("dataset_overview")
        except Exception:
            pass

    return {
        "cannot_answer":  False,
        "reason":         "",
        "charts":         chart_responses,
        "kpis":           kpi_responses,
        "insight":        insight,
        "brief_insights": brief_insights,
        "suggestions":    suggestions,
        "dataset_overview": dataset_overview,
        "provider":       stage1.get("provider_used", "groq"),
        "_chart_records": chart_records,  # internal ??? stripped before API response
    }


# ?????? Cannot-answer detection (time-series guard) ????????????????????????????????????????????????????????????????????????????????????????????????

def _check_time_series(prompt: str, schema: SchemaPayload) -> Optional[str]:
    if schema.has_date_column:
        return None
    prompt_lower = prompt.lower()
    for phrase in TIME_TREND_PHRASES:
        if phrase in prompt_lower:
            return (
                "This dataset has no date/time column ??? time-series trends cannot be computed. "
                "Note: monthly_online_orders and monthly_store_visits are per-customer counts, "
                "not timestamps."
            )
    return None


# ?????? Suggestions ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

def generate_suggestions(prompt: str, charts: List[Dict], schema: SchemaPayload) -> List[str]:
    if not charts:
        return []
    chart_summary = "; ".join(
        f"{c.get('title', '')} ({c.get('type', '')})"
        for c in charts[:3]
    )
    suggestion_prompt = f"""A BI dashboard just answered: "{prompt}"
Charts shown: {chart_summary}
Dataset columns include: {', '.join(c.safe_name for c in schema.columns[:15])}

Suggest exactly 3 short follow-up questions the user might ask next.
Questions should be specific to the data shown, not generic.
Respond with ONLY a JSON array of 3 strings:
["question 1", "question 2", "question 3"]"""

    try:
        result = call_llm(suggestion_prompt)
        if isinstance(result, list):
            return [str(q) for q in result[:3]]
        for key in ("suggestions", "questions", "follow_ups", "items"):
            if key in result and isinstance(result[key], list):
                return [str(q) for q in result[key][:3]]
        return []
    except Exception:
        return []


# ?????? Public pipeline functions ???????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

def run_query(prompt: str, session_id: str) -> Dict:
    session = get_session(session_id)
    if not session:
        return {"error": "Session not found or expired. Please reload the dataset."}

    schema = session.schema

    # Time-series guard (fast check, no LLM call needed)
    ts_reason = _check_time_series(prompt, schema)
    if ts_reason:
        return {
            "cannot_answer": True, "reason": ts_reason,
            "charts": [], "kpis": [], "insight": "", "suggestions": [],
        }

    ctx    = build_schema_context(schema, query=prompt)
    result = _run_two_stage(prompt, schema, session.db_path, ctx, last_contexts=session.last_contexts)
    chart_records = result.pop("_chart_records", [])


    if not result.get("cannot_answer"):
        session.last_charts = chart_records
        session.last_prompt = prompt
        session.history.append(QueryRecord(
            prompt=prompt, timestamp=time.time(),
            chart_specs=[{"title": c.title, "type": c.chart_type} for c in chart_records],
            kpi_specs=[{"label": k["label"], "format": k["format"]}
                       for k in result.get("kpis", [])],
            insight=result.get("insight", ""),
        ))
        
        # Track context for follow-up questions
        used_cols = set()
        for c in result.get("charts", []):
            if c.get("x_col"): used_cols.add(c["x_col"])
            for yc in c.get("y_cols", []): used_cols.add(yc)
            if c.get("color_col"): used_cols.add(c["color_col"])
            
        session.last_contexts.append({
            "prompt": prompt,
            "sql": result.get("charts", [])[0].get("sql", "") if result.get("charts") else "",
            "columns": list(used_cols)
        })
        session.last_contexts = session.last_contexts[-3:]
    else:
        session.history.append(QueryRecord(
            prompt=prompt, timestamp=time.time(), chart_specs=[], kpi_specs=[],
            insight="", cannot_answer=True, reason=result.get("reason", ""),
        ))

    set_session(session_id, session)
    return result


def run_refine(message: str, session_id: str, original_prompt: str) -> Dict:
    session = get_session(session_id)
    if not session:
        return {"error": "Session not found or expired. Please reload the dataset."}
    if not session.last_charts:
        return {"error": "No previous charts found. Run a query first."}

    schema  = session.schema
    from query_pipeline import _check_time_series
    ts_reason = _check_time_series(message, schema)
    if ts_reason:
        return {
            "cannot_answer": True, "reason": ts_reason,
            "charts": [], "kpis": [], "insight": "",
        }

    # For refine, we build a modified prompt that includes the current dashboard context
    # and pass it through the same two-stage pipeline
    current_context = "\n".join(
        f"Current chart {i}: {c.title}\nSQL: {c.sql}"
        for i, c in enumerate(session.last_charts, 1)
    )
    combined_prompt = (
        f"{original_prompt}\n\n"
        f"MODIFICATION REQUEST: {message}\n\n"
        f"EXISTING CHARTS TO MODIFY:\n{current_context}"
    )

    ctx    = build_schema_context(schema, query=message)
    result = _run_two_stage(combined_prompt, schema, session.db_path, ctx, last_contexts=session.last_contexts)

    chart_records = result.pop("_chart_records", [])
    result.pop("suggestions", None)  # refine doesn't return suggestions

    if not result.get("cannot_answer"):
        session.last_charts = chart_records
        session.last_prompt = f"{original_prompt} ??? {message}"
        set_session(session_id, session)

    return result


def run_chat(message: str, history: List[Dict], session_id: str, context: Optional[Dict] = None) -> Dict:
    session = get_session(session_id)
    if not session:
        return {"error": "Session not found or expired. Please reload the dataset."}

    schema = session.schema
    # Add truncated schema + current view context to save tokens
    schema_ctx = build_schema_context(schema, query=message)
    if len(schema_ctx) > 3000:
        schema_ctx = schema_ctx[:3000] + "\n... (schema truncated for brevity)"
    ctx = schema_ctx

    history_text = ""
    if history:
        history_text = "CHAT HISTORY:\n" + "\n".join(
            f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
            for msg in history[-6:]  # Keep last 6 messages for context
        )

    # Prepare Dashboard Context for the Analyst
    dashboard_ctx = ""
    if context:
        charts = [c.get("title", "Untitled") for c in context.get("charts", [])]
        insight = context.get("insight", "No overview yet.")
        dashboard_ctx = f"""
CURRENT DASHBOARD STATE:
- ACTIVE INSIGHTS: {insight}
- VISIBLE CHARTS: {", ".join(charts) if charts else "None"}
"""

    prompt = f"""You are a resident Data Analyst for the InsightFlow dashboard.
You help users understand their dataset and explain the insights visible on their screen.

SCHEMA CONTEXT:
{ctx}
{dashboard_ctx}

{history_text}

USER MESSAGE: {message}

Rules:
- Give a detailed, helpful, and highly structured answer.
- ADOPT THE ANALYST PERSONA: Use the provided "CURRENT DASHBOARD STATE" to explain what is happening in the charts.
- If the user asks "Why is there a spike?" or "What does this mean?", use the results in the ACTIVE INSIGHTS to explain it.
- Use **Markdown** formatting extensively (bold, bullets, tables).
- If you don't have enough data to answer a specific numeric question, help them write a prompt for the main search bar to get that data.
- Keep your response professional yet conversational.

Respond with ONLY this JSON:
{{"response": "your analytical response here"}}
"""
    try:
        result = call_llm(prompt)
        if result.get("cannot_answer"):
            return {"response": result.get("reason", "I'm sorry, I couldn't process that.")}
        return {"response": result.get("response", "I'm sorry, I couldn't generate a response.")}
    except Exception as e:
        return {"response": f"Error communicating with AI: {e}"}


# ?????? Legacy single-pass prompt builders (kept for reference) ?????????????????????????????????????????????????????????

def build_query_prompt(schema_context: str, user_prompt: str, table_name: str) -> str:
    """Legacy ??? no longer called by run_query. Kept for backward compatibility."""
    return _prompt_stage1(schema_context, user_prompt, table_name)


def build_refine_prompt(schema_context: str, original_prompt: str,
                        current_charts: list, message: str, table_name: str) -> str:
    """Legacy ??? no longer called by run_refine. Kept for backward compatibility."""
    return f"Refine: {original_prompt} ??? {message}"


def run_auto_report(session_id: str) -> Dict:
    """
    Generate a comprehensive multi-chart business report autonomously.
    Calculates variety of charts (Trend, Distribution, Categorical, Top-K) + KPIs + Insights.
    """
    session = get_session(session_id)
    if not session:
        return {"error": "Session not found or expired. Please reload the dataset."}

    schema = session.schema
    ctx    = build_schema_context(schema)

    # We want a comprehensive business report.
    # We'll ask the LLM to generate exactly 4 charts covering different areas.
    report_prompt = f"""Generate an Executive Report for: {schema.dataset_name}.
REQUIRED (exactly 4 diverse charts):
1. TREND: Primary metric over time (use Date column).
2. SEGMENTS: Numeric metric by major Cat dimension.
3. COMPARISON: Compare 2-3 segments across a metric.
4. TOP-K: Top 5 items by success metric.

ALSO:
- 4 primary KPIs.
- 3-5 brief_insights (one-liners).
- 3-5 bulleted 'insight' takeaways (*).
- 3 suggestions for follow-up.
"""

    result = _run_two_stage(report_prompt, schema, session.db_path, ctx)

    # Strip internal-only fields that contain non-serializable dataclass objects
    # (run_query does this via .pop() ??? auto-report was missing it, causing HTTP 500)
    if isinstance(result, dict):
        result.pop("_chart_records", None)
        result["is_auto_report"] = True

    return result
