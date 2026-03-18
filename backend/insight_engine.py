"""
insight_engine.py
─────────────────────────────────────────────────────────
Analyzes query results to generate structured business insights.
Extracts headlines, bullets, and recommendations using LLM,
supplemented by deterministic statistical checks.
"""
from typing import Dict, List, Any
import math

def _get_numeric_cols(rows: List[Dict]) -> List[str]:
    if not rows: return []
    cols = []
    for k, v in rows[0].items():
        if v is not None:
            try:
                float(v)
                cols.append(k)
            except (ValueError, TypeError):
                pass
    return cols

def _detect_trends(rows: List[Dict]) -> List[str]:
    if len(rows) < 3: return []
    trends = []
    num_cols = _get_numeric_cols(rows)
    for col in num_cols:
        vals = []
        for r in rows:
            v = r.get(col)
            if v is not None:
                try: vals.append(float(v))
                except: vals.append(None)
        
        valid_vals = [v for v in vals if v is not None]
        if len(valid_vals) < 3: continue
        
        # Check monotonic increase/decrease
        is_inc = all(valid_vals[i] <= valid_vals[i+1] for i in range(len(valid_vals)-1))
        is_dec = all(valid_vals[i] >= valid_vals[i+1] for i in range(len(valid_vals)-1))
        
        if is_inc and valid_vals[-1] > valid_vals[0]:
            trends.append(f"{col} shows a consistent upward trend.")
        elif is_dec and valid_vals[0] > valid_vals[-1]:
            trends.append(f"{col} shows a consistent downward trend.")
            
    return trends

def _detect_anomalies(rows: List[Dict]) -> List[str]:
    if len(rows) < 4: return []
    anomalies = []
    num_cols = _get_numeric_cols(rows)
    for col in num_cols:
        vals = []
        for r in rows:
            v = r.get(col)
            if v is not None:
                try: vals.append(float(v))
                except: pass
                
        if len(vals) < 4: continue
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0: continue
        
        for idx, r in enumerate(rows):
            v = r.get(col)
            if v is not None:
                try: 
                    num = float(v)
                    z_score = (num - mean) / std_dev
                    if abs(z_score) > 2.0:
                        # Grab the first text column as a label, if any
                        label = f"Row {idx+1}"
                        for k, kv in r.items():
                            if k not in num_cols and kv:
                                label = str(kv)
                                break
                        
                        direction = "high" if z_score > 0 else "low"
                        anomalies.append(f"Anomaly detected: {label} has unusually {direction} {col} ({num:.2f}, >2σ from mean).")
                except: pass
    return anomalies

def build_insight_prompt(user_prompt: str, charts_summary: str, rows: List[Dict]) -> str:
    trends = _detect_trends(rows)
    anomalies = _detect_anomalies(rows)
    
    context_additions = []
    if trends:
        context_additions.append("STATISTICAL TRENDS:\n" + "\n".join(f"- {t}" for t in trends))
    if anomalies:
        context_additions.append("STATISTICAL ANOMALIES:\n" + "\n".join(f"- {a}" for a in anomalies))
        
    stat_context = "\n\n".join(context_additions)
    
    return f"""Write a structured business insight based on these query results.

ORIGINAL QUESTION: {user_prompt}

RESULTS:
{charts_summary}

{stat_context}

Rules:
- Cite specific numbers from the results
- Be honest — if results are weak or inconclusive, say so
- Write as a business analyst, not a data scientist
- Incorporate the statistical trends/anomalies if they are relevant

Respond with ONLY this JSON:
{{
  "headline": "A punchy, one-line summary of the main finding (max 10 words)",
  "bullets": [
    "Specific data point finding 1",
    "Specific data point finding 2"
  ],
  "recommendation": "One immediate business action or takeaway based on these findings"
}}
"""
