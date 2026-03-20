"""
processor_v2.py
---------------------------------------------------------
Robust chart correction pipeline.
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional


def pearson_r(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 3: return None
    try:
        mx, my = sum(xs) / n, sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        dy = math.sqrt(sum((y - my) ** 2 for y in ys))
        return num / (dx * dy) if (dx * dy) != 0 else None
    except: return None


def linear_regression(xs: List[float], ys: List[float]) -> Optional[tuple[float, float]]:
    n = len(xs)
    if n < 2: return None
    try:
        mx, my = sum(xs) / n, sum(ys) / n
        dx_sq = sum((x - mx) ** 2 for x in xs)
        if dx_sq == 0: return None
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / dx_sq
        return slope, my - slope * mx
    except: return None


def pivot_for_grouped_bar(rows: List[Dict], x_col: str, color_col: str, y_col: str) -> List[Dict]:
    if not rows or not x_col or not color_col or not y_col: return rows
    pivot: Dict[str, Dict[str, Any]] = {}
    x_order, colors = [], []
    for r in rows:
        if not isinstance(r, dict): continue
        xv, cv, yv = str(r.get(x_col, "")), str(r.get(color_col, "")), r.get(y_col, 0)
        if xv not in pivot:
            pivot[xv] = {}
            x_order.append(xv)
        pivot[xv][cv] = yv
        if cv not in colors: colors.append(cv)
    return [{x_col: x, **{c: pivot[x].get(c, 0) for c in colors}} for x in x_order]


def coerce_kpi_value(raw_rows: List[Dict], fmt: str) -> Any:
    if not raw_rows: return None
    try:
        val = next(iter(raw_rows[0].values()), None)
        if fmt == "text": return str(val) if val is not None else "N/A"
        f = float(val)
        return int(f) if fmt == "number" and f == int(f) else f
    except:
        try: return str(next(iter(raw_rows[0].values()), "N/A"))
        except: return "N/A"


def post_process_chart(spec: Dict, rows: List[Dict]) -> Dict:
    if not rows:
        spec["warning"] = "no_matching_data"
        spec["rows"] = []
        return spec

    ctype = spec.get("type", "bar")
    xcol  = spec.get("x_col", "")
    ccol  = spec.get("color_col")
    ycols = spec.get("y_cols", [])

    if ctype == "grouped_bar" and ccol and ycols:
        try:
            rows = pivot_for_grouped_bar(rows, xcol, ccol, ycols[0])
            if rows: spec["y_cols"] = [k for k in rows[0] if k != xcol]
        except Exception as e:
            spec["note"] = f"Pivot failed: {e}"

    if len(rows) > 200:
        spec["warning"] = f"Too many rows ({len(rows)}). Showing top 20."
        rows = rows[:20]

    if len(rows) > 50: rows = rows[:20]

    if ctype == "pie" and ycols:
        ycol = ycols[0]
        if 5 < len(rows) <= 12:
            try:
                sorted_r = sorted(rows, key=lambda r: float(r.get(ycol) or 0), reverse=True)
                top = sorted_r[:5]
                tail = sum(float(r.get(ycol) or 0) for r in sorted_r[5:])
                if tail > 0: rows = top + [{xcol: "Other", ycol: tail}]
            except: pass

    if ctype == "pie" and ycols:
        ycol = ycols[0]
        try:
            tot = sum(float(r.get(ycol) or 0) for r in rows)
            if tot > 0 and (max(float(r.get(ycol) or 0) for r in rows)/tot) > 0.6:
                spec["type"] = "bar"
                spec["_type_corrected"] = True
            elif len(rows) > 8:
                spec["type"] = "bar"
                spec["_type_corrected"] = True
        except: pass

    if spec.get("type") == "scatter" and ycols:
        try:
            ycol = ycols[0]
            xs, ys = [], []
            for r in rows:
                try:
                    xs.append(float(r[xcol]))
                    ys.append(float(r[ycol]))
                except: pass
            rv = pearson_r(xs, ys)
            if rv is not None:
                str_ = "strong" if abs(rv) >= 0.5 else "mod" if abs(rv) >= 0.3 else "weak"
                dir_ = "pos" if rv >= 0 else "neg"
                spec["correlation_note"] = f"r={rv:.2f} ({str_} {dir_})"
        except: pass

    if spec.get("type") == "line" and ycols:
        try:
            ycol = ycols[0]
            v_x = [i for i, r in enumerate(rows) if r.get(ycol) is not None]
            v_y = [float(rows[i].get(ycol)) for i in v_x]
            if len(v_y) >= 3:
                model = linear_regression(v_x, v_y)
                if model:
                    slope, intercept = model
                    fkey = f"{ycol}_forecast"
                    rows[-1][fkey] = rows[-1].get(ycol)
                    for step in range(1, 4):
                        rows.append({xcol: f"Forecast +{step}", fkey: round(slope*(v_x[-1]+step) + intercept, 2)})
                    if fkey not in spec["y_cols"]: spec["y_cols"].append(fkey)
        except: pass

    if "product_availability_online" in spec.get("sql", "").lower():
        spec["note"] = (spec.get("note", "") + " (!) Ambiguous mapping.").strip()

    spec["rows"] = rows
    return spec
