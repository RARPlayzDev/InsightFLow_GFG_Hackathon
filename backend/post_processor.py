"""
post_processor.py
─────────────────────────────────────────────────────────
9-rule chart correction pipeline that runs AFTER SQL execution.
Rules are applied in order:
  1. Empty result         → set warning, return early
  2. Grouped bar pivot    → long → wide form for Recharts
  3. Raw row dump guard   → block >200 rows without aggregation
  4. Truncate large       → cap bar/line/area at 20 rows
  5. Pie tail merge       → merge tail slices into "Other" (5 < n ≤ 12)
  6. Pie → bar            → convert if >8 categories OR dominant slice >60%
  7. Scatter correlation  → compute Pearson r, add note
  8. Line Forecasting     → 3-step linear regression projection
  9. Ambiguous flag       → append ⚠ note for flagged columns
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional


# ── Pearson r ─────────────────────────────────────────────────────

def pearson_r(xs: List[float], ys: List[float]) -> Optional[float]:
    """
    Returns Pearson correlation coefficient, or None if insufficient data
    or if either variable has zero variance.
    """
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def linear_regression(xs: List[float], ys: List[float]) -> Optional[tuple[float, float]]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    dx_sq = sum((x - mx) ** 2 for x in xs)
    if dx_sq == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / dx_sq
    intercept = my - slope * mx
    return slope, intercept


# ── Pivot for grouped bar ─────────────────────────────────────────

def pivot_for_grouped_bar(
    rows: List[Dict], x_col: str, color_col: str, y_col: str
) -> List[Dict]:
    """
    Convert long-form SQL result to wide-form for Recharts grouped bar.

    Input (long):                Output (wide):
    x_col | color_col | y_col   x_col | Male | Female | Other
    Tier1  | Male      | 74000   Tier1 | 74000 | 71000 | 68000
    Tier1  | Female    | 71000   ...
    """
    pivot: Dict[str, Dict[str, Any]] = {}
    x_order: List[str] = []
    color_vals: List[str] = []

    for row in rows:
        x_val = str(row.get(x_col, ""))
        c_val = str(row.get(color_col, ""))
        y_val = row.get(y_col, 0)

        if x_val not in pivot:
            pivot[x_val] = {}
            x_order.append(x_val)
        pivot[x_val][c_val] = y_val

        if c_val not in color_vals:
            color_vals.append(c_val)

    return [
        {x_col: x_val, **{c: pivot[x_val].get(c, 0) for c in color_vals}}
        for x_val in x_order
    ]


# ── Coerce KPI scalar ─────────────────────────────────────────────

def coerce_kpi_value(raw_rows: List[Dict], fmt: str) -> Any:
    """
    Extract a single scalar from a KPI SQL result row.
    Returns None if the result set is empty.
    """
    if not raw_rows:
        return None
    val = next(iter(raw_rows[0].values()), None)
    if fmt == "text":
        return str(val) if val is not None else "N/A"
    if val is None:
        return None
    try:
        f = float(val)
        # Return int for whole-number counts (cleaner display)
        return int(f) if fmt == "number" and f == int(f) else f
    except (TypeError, ValueError):
        return str(val)


# ── Main post-processor ───────────────────────────────────────────

def post_process_chart(chart_spec: Dict, rows: List[Dict]) -> Dict:
    """
    Apply all 8 correction rules in order.
    Mutates and returns chart_spec with 'rows' added.

    Important: y_cols is always read fresh from chart_spec at the point of use
    in each rule, not cached at the top of the function. This ensures Rule 6
    (which updates chart_spec["y_cols"] after pivot) is visible to Rule 7.
    """
    chart_type = chart_spec.get("type", "bar")
    x_col = chart_spec.get("x_col", "")
    color_col = chart_spec.get("color_col")

    # ── Rule 1: Empty result ──────────────────────────────────────
    if not rows:
        chart_spec["warning"] = "no_matching_data"
        chart_spec["rows"] = []
        return chart_spec

    # ── Rule 2: Grouped bar long → wide pivot ─────────────────────
    if chart_type == "grouped_bar" and color_col:
        y_cols = chart_spec.get("y_cols", [])
        y_col = y_cols[0] if y_cols else None
        if y_col:
            rows = pivot_for_grouped_bar(rows, x_col, color_col, y_col)
            # Update y_cols to reflect the pivoted series (color dimension values)
            if rows:
                chart_spec["y_cols"] = [k for k in rows[0] if k != x_col]

    # ── Rule 3: Raw row dump guard ────────────────────────────────
    if len(rows) > 200:
        chart_spec["warning"] = (
            f"Query returned {len(rows)} rows — too many to visualise. "
            "Add GROUP BY or a more specific WHERE clause."
        )
        chart_spec["rows"] = rows[:20]
        return chart_spec

    # ── Rule 4: Truncate large aggregated results ─────────────────
    if len(rows) > 50 and chart_type in ("bar", "line", "area", "grouped_bar"):
        rows = rows[:20]

    # ── Rule 4: Pie tail merge ────────────────────────────────────
    if chart_type == "pie":
        y_cols = chart_spec.get("y_cols", [])
        y_col = y_cols[0] if y_cols else None
        if y_col and 5 < len(rows) <= 12:
            try:
                sorted_rows = sorted(
                    rows, key=lambda r: float(r.get(y_col) or 0), reverse=True
                )
                top = sorted_rows[:5]
                tail_sum = sum(float(r.get(y_col) or 0) for r in sorted_rows[5:])
                rows = top + ([{x_col: "Other", y_col: tail_sum}] if tail_sum > 0 else [])
            except (TypeError, ValueError):
                pass  # leave rows unchanged if values aren't numeric

    # ── Rule 5: Pie → bar (dominant slice or too many categories) ─
    if chart_type == "pie":
        y_cols = chart_spec.get("y_cols", [])
        y_col = y_cols[0] if y_cols else None
        convert_to_bar = len(rows) > 8
        if not convert_to_bar and y_col:
            try:
                total = sum(float(r.get(y_col) or 0) for r in rows)
                if total > 0:
                    max_share = max(float(r.get(y_col) or 0) for r in rows) / total
                    convert_to_bar = max_share > 0.6
            except (TypeError, ValueError):
                pass
        if convert_to_bar:
            chart_type = "bar"
            chart_spec["type"] = "bar"
            chart_spec["_type_corrected"] = True  # flag for UI badge



    # ── Rule 7: Scatter Pearson r ─────────────────────────────────
    # Read y_cols fresh — Rule 6 may have updated chart_spec["y_cols"]
    if chart_type == "scatter":
        y_cols = chart_spec.get("y_cols", [])
        y_col = y_cols[0] if y_cols else None
        if y_col:
            xs, ys = [], []
            for r in rows:
                try:
                    xs.append(float(r[x_col]))
                    ys.append(float(r[y_col]))
                except (KeyError, TypeError, ValueError):
                    pass
            r_val = pearson_r(xs, ys)
            if r_val is not None:
                strength = (
                    "strong" if abs(r_val) >= 0.5
                    else "moderate" if abs(r_val) >= 0.3
                    else "weak / no"
                )
                direction = "positive" if r_val >= 0 else "negative"
                chart_spec["correlation_note"] = (
                    f"Pearson r = {r_val:.3f} — {strength} {direction} correlation"
                )

    # ── Rule 8: Line Chart Forecasting ────────────────────────────
    if chart_type == "line":
        y_cols = chart_spec.get("y_cols", [])
        if y_cols:
            y_col = y_cols[0]
            xs = list(range(len(rows)))
            ys = []
            valid_x = []
            for i, r in enumerate(rows):
                try:
                    val = float(r.get(y_col))
                    ys.append(val)
                    valid_x.append(i)
                except (TypeError, ValueError):
                    pass
            
            if len(ys) >= 3:
                model = linear_regression(valid_x, ys)
                if model:
                    slope, intercept = model
                    forecast_key = f"{y_col}_forecast"
                    last_obj = rows[-1]

                    # Link the last actual data point so the line connects seamlessly
                    last_obj[forecast_key] = last_obj.get(y_col)

                    # Generate 3 future points
                    for step in range(1, 4):
                        new_x = (xs[-1] if xs else 0) + step
                        pred_y = slope * new_x + intercept
                        
                        new_row = {
                            x_col: f"Next +{step}",
                            forecast_key: round(pred_y, 2)
                        }
                        rows.append(new_row)
                    
                    if forecast_key not in chart_spec["y_cols"]:
                        chart_spec["y_cols"].append(forecast_key)
                    
                    chart_spec["note"] = (chart_spec.get("note", "") + " 📈 Includes 3-step forecast projection.").strip()

    # ── Rule 9: Ambiguous column flag ─────────────────────────────
    sql = chart_spec.get("sql", "")
    if "product_availability_online" in sql.lower():
        existing_note = chart_spec.get("note", "")
        suffix = "⚠ product_availability_online has ambiguous meaning per the data dictionary."
        chart_spec["note"] = (existing_note + " " + suffix).strip()

    chart_spec["rows"] = rows
    return chart_spec
