"""
schema_context.py
─────────────────────────────────────────────────────────
Builds the schema context string injected into every LLM prompt.

Key design decision: every continuous column gets a standardised alias
(e.g. "age" → alias "age_group"). The LLM is told to use this alias in
both the SQL (AS "age_group") and the x_col field. This eliminates the
hallucinated alias problem where the LLM invents "age_bucket", "age_range"
etc. which our validator then rejects as non-existent columns.
"""
from __future__ import annotations
import re
from session_store import SchemaPayload

GFG_DATASET_NOTES = """
DATASET NOTES (pre-loaded GFG dataset):
- Psychometric scores (1-10): discount_sensitivity, return_frequency, delivery_fee_sensitivity,
  free_return_importance, impulse_buying_score, need_touch_feel_score, brand_loyalty_score,
  environmental_awareness, time_pressure_level, online_payment_trust_score, tech_savvy_score
  → All show r < 0.01 vs spending. Never claim predictive power for these.
- product_availability_online: ambiguous meaning — add hedging language in insight
- avg_delivery_days (1–7): real delivery days, NOT psychometric
- monthly_online_orders / monthly_store_visits: per-customer counts per month, NOT timestamps
- shopping_preference distribution: Store≈87%, Online≈10%, Hybrid≈3% → use bar chart, not pie
""".strip()

ROLE_HINTS = {
    "continuous": "MUST bucket with CASE WHEN — see bucket_sql and alias below",
    "score":      "AVG() for mean, COUNT(*) GROUP BY for distribution (1–10 scale)",
    "measure":    "COUNT(*) GROUP BY or AVG()",
    "dimension":  "GROUP BY / WHERE filter",
    "id":         "never SUM or AVG",
    "datetime":   "can use strftime for grouping",
    "text":       "label only — do not aggregate",
}


def _alias_for(safe_name: str) -> str:
    """
    Return a standardised SQL alias for a continuous column.
    This alias is used in both the SELECT (AS "alias") and the x_col field.
    Using a fixed alias eliminates LLM hallucination of arbitrary names.
    """
    # Map known columns to clean display aliases
    _KNOWN = {
        "age":              "age_group",
        "monthly_income":   "income_group",
        "daily_internet_hours": "internet_hours_group",
        "smartphone_usage_years": "usage_years_group",
        "social_media_hours": "social_hours_group",
        "avg_online_spend":  "online_spend_group",
        "avg_store_spend":   "store_spend_group",
        "monthly_online_orders": "orders_group",
        "monthly_store_visits":  "visits_group",
    }
    if safe_name in _KNOWN:
        return _KNOWN[safe_name]
    # Generic fallback: append _group
    return safe_name + "_group"


def build_schema_context(schema: SchemaPayload, query: str = "") -> str:
    """
    Build the schema context string for LLM prompts.

    Token trimming: when a query is provided, columns whose safe_name or
    original_name has NO keyword overlap with the query are sent as a
    one-line summary instead of full detail (bucket_sql, alias, USAGE).
    This cuts token count ~50-60% on focused queries while keeping all
    column names visible so the LLM can still reference them.
    Always sends full detail for: continuous columns (need bucket_sql),
    and columns explicitly mentioned in the query.
    """
    lines = [
        f"Table: {schema.table_name} ({schema.row_count:,} rows)",
        f"Dataset: {schema.dataset_name}",
        "",
        "CONSTRAINTS:",
    ]

    if not schema.has_date_column:
        lines += [
            "- NO date/time columns. Time-series queries CANNOT be answered.",
            "  NOTE: monthly_online_orders and monthly_store_visits are per-customer counts, NOT timestamps.",
        ]

    sp_col = next((c for c in schema.columns if c.safe_name == "shopping_preference"), None)
    if sp_col:
        lines.append("- shopping_preference: Store≈87%, Online≈10%, Hybrid≈3% → bar chart, not pie")

    lines += ["", "COLUMNS:"]

    # Build keyword set from query for trimming
    query_words = set(re.sub(r'[^a-z0-9_]', ' ', query.lower()).split()) if query else set()

    for col in schema.columns:
        sample_str = ", ".join(str(s) for s in col.samples[:3]) if col.samples else "N/A"
        ambig      = " ⚠ AMBIGUOUS" if col.is_ambiguous else ""

        # Determine if this column is "in focus" for this query
        col_words = set(col.safe_name.replace('_', ' ').split()) | {col.safe_name}
        in_focus  = (
            not query_words                          # no query — send everything
            or bool(col_words & query_words)         # column name mentioned
            or col.role == "continuous"              # always needs bucket_sql
            or col.role in ("score", "measure")      # likely aggregation targets
        )

        lines.append(
            f'  "{col.safe_name}" | {col.original_name} | {col.role} | '
            f'{col.nunique} unique | samples: {sample_str}{ambig}'
        )

        if in_focus:
            hint = ROLE_HINTS.get(col.role, "")
            if hint:
                lines.append(f"    → {hint}")
            if col.bucket_sql:
                alias = _alias_for(col.safe_name)
                lines.append(f'    bucket_sql:  {col.bucket_sql}')
                lines.append(f'    alias:       "{alias}"')
                lines.append(
                    f'    USAGE:       SELECT {col.bucket_sql} AS "{alias}", COUNT(*) '
                    f'FROM {schema.table_name} GROUP BY "{alias}"'
                )
                lines.append(f'    x_col:       "{alias}"   ← use EXACTLY this in x_col field')

    is_gfg = (
        "customer_behaviour" in schema.table_name.lower()
        or "customer_behavior" in schema.table_name.lower()
    )
    if is_gfg:
        lines += ["", GFG_DATASET_NOTES]

    return "\n".join(lines)


def get_valid_aliases(schema: SchemaPayload) -> set:
    """
    Return all valid x_col values: schema safe_names PLUS the standardised
    aliases for continuous columns. Used by detect_cannot_answer to avoid
    false positives when the LLM correctly uses an alias.
    """
    valid = {c.safe_name for c in schema.columns}
    for col in schema.columns:
        if col.bucket_sql:
            valid.add(_alias_for(col.safe_name))
    return valid