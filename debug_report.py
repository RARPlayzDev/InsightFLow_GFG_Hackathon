import sys
import os
import traceback
from pathlib import Path

# Add backend to path
backend_path = r"d:\Kaarthi\Dev Space\InsightFlow-Gfg_Hackathon-main\backend"
sys.path.append(backend_path)

# Mock environment
os.environ["SESSIONS_DIR"] = os.path.join(backend_path, "..", "sessions")

try:
    from query_pipeline import run_auto_report
    from session_store import set_session, SessionData
    from ingest import ingest_csv

    sid = "debug-script-session"
    print(f"Testing run_auto_report for sid: {sid}")
    
    # 1. Manually ingest
    csv_path = Path(backend_path).parent / "data" / "Customer_Behaviour__Online_vs_Offline_.csv"
    if not csv_path.exists():
        print(f"Error: CSV not found at {csv_path}")
        sys.exit(1)
        
    raw = csv_path.read_bytes()
    db_path = os.path.join(backend_path, "..", "sessions", f"{sid}.db")
    
    # Ensure sessions folder exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    schema = ingest_csv(raw, csv_path.name, db_path)
    set_session(sid, SessionData(schema=schema, db_path=db_path))
    
    print(f"Dataset ingested. DB: {db_path}")
    
    # 2. Run report
    result = run_auto_report(sid)
    print("Success! Result keys:", result.keys())
    # Try to simulate JSON dump as well to check for serialization errors
    import json
    json.dumps(result)
    print("JSON Serialization OK!")
    
except Exception:
    print("CRASH DETECTED!")
    traceback.print_exc()
