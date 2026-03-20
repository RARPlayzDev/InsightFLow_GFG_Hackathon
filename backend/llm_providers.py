"""
llm_providers.py
─────────────────────────────────────────────────────────
Multi-provider LLM ladder with automatic failover.
Providers tried in order: Groq keys -> Gemini keys.
Raw response preview: {raw[:150]!r}
Both use OpenAI-compatible chat completions format.
"""

import os
import json
import time
import copy
import hashlib
import sys
import traceback
print("LLM_PROVIDERS VERSION: 15.2 (ASCII-SAFE)")
from typing import Dict, List, Optional
import httpx

PROVIDERS = [
    {
        "name": "groq", "icon": "⚡",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "env_keys": ["GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3"],
        "model_env": "GROQ_MODEL",
        "default_model": "llama-3.3-70b-versatile",
    },
    {
        "name": "gemini", "icon": "🔷",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "env_keys": ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"],
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-2.0-flash",
    },
]

_CACHE_FILE = os.path.join(os.path.dirname(__file__), "llm_cache.json")
_RESPONSE_CACHE: Dict[str, List] = {} # {key: [result_dict, timestamp]}

def _load_cache():
    global _RESPONSE_CACHE
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _RESPONSE_CACHE = json.load(f)
        except Exception:
            _RESPONSE_CACHE = {}

def _save_cache():
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            # Keep only last 24 hours
            now = time.time()
            fresh = {k: v for k, v in _RESPONSE_CACHE.items() if (now - v[1]) < 86400}
            json.dump(fresh, f)
    except Exception:
        pass

_load_cache()

def _clean_env(key: str, default: str = "") -> str:
    v = os.getenv(key, default).strip()
    if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
        v = v[1:-1].strip()
    return v

def _is_valid_key(val: str) -> bool:
    """Check if a key is a real key or just a placeholder from .env.example."""
    if not val or len(val) < 15:
        return False
    placeholders = ["your_", "api_here", "optional", "sk-", "gsk-"]
    # If it contains "your_" or "api_here" but DOES NOT start with common prefixes correctly
    v_low = val.lower()
    if "your_" in v_low or "api_here" in v_low or "optional" in v_low:
        return False
    return True

def _get_all_keys() -> List[Dict]:
    keys = []
    for provider in PROVIDERS:
        for env_key in provider["env_keys"]:
            val = _clean_env(env_key)
            if _is_valid_key(val):
                keys.append({
                    "provider": provider["name"],
                    "icon": provider["icon"],
                    "base_url": provider["base_url"],
                    "model": _clean_env(provider["model_env"], provider["default_model"]),
                    "api_key": val
                })
    return keys

def _cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]

def _extract_json(text: str) -> Dict:
    import re
    text = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`").strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found. Preview: {text[:200]!r}")
    return json.loads(text[start : end + 1])

def call_llm_ladder(prompt: str) -> Dict:
    ck = _cache_key(prompt)
    now = time.time()
    
    # 24-hour TTL cache
    if ck in _RESPONSE_CACHE:
        cached_res, timestamp = _RESPONSE_CACHE[ck]
        if now - timestamp < 86400:
            print(f"[LLM] Cache Hit ({ck}) - using persistent result")
            return copy.deepcopy(cached_res)
        else:
            del _RESPONSE_CACHE[ck]

    keys = _get_all_keys()
    if not keys:
        return {"cannot_answer": True, "reason": "No API keys configured (Groq or Gemini). Make sure to set them in .env."}

    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Business Intelligence analyst. "
                    "You MUST respond with ONLY a valid JSON object. "
                    "No markdown, no backticks, no explanation — raw JSON only."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"}
    }
    
    # Try keys in order
    for idx, key_data in enumerate(keys):
        model = key_data["model"]
        api_key = key_data["api_key"]
        p_name = key_data["provider"]
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        req_payload = copy.deepcopy(payload)
        req_payload["model"] = model
        
        print(f"[LLM] >> {p_name.capitalize()}/{model} (Key {idx+1}/{len(keys)})")
        
        try:
            r = httpx.post(key_data["base_url"], json=req_payload, headers=headers, timeout=45.0)
            # ASCII-safe log
            print(f"[LLM] << HTTP {r.status_code}")
            
            if r.status_code == 429:
                print(f"[LLM] 429 Rate limited, rotating to next key...", file=sys.stderr)
                continue
                
            if r.status_code != 200:
                print(f"[LLM] ERROR {r.status_code}: {r.text[:300]}", file=sys.stderr)
                continue
                
            choices = r.json().get("choices", [])
            if not choices:
                continue
                
            raw = choices[0].get("message", {}).get("content", "")
            if not raw.strip():
                continue
                
            result = _extract_json(raw)
            result["provider_used"] = p_name
            
            # Continuous result preview for terminal (ASCII-safe for Windows)
            preview = (raw[:150] + "...") if len(raw) > 150 else raw
            safe_preview = "".join(c for c in preview if ord(c) < 128)
            print(f"[LLM] SUCCESS - {p_name.upper()}\n[RESULT] {safe_preview}")
            
            _RESPONSE_CACHE[ck] = (copy.deepcopy(result), now)
            _save_cache()
            return copy.deepcopy(result)
            
        except httpx.ReadTimeout:
            print(f"[LLM] ReadTimeout", file=sys.stderr)
            continue
        except httpx.ConnectError as e:
            print(f"[LLM] ConnectError: {e}", file=sys.stderr)
            continue
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[LLM] Parse error: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[LLM] Unexpected error: {e}", file=sys.stderr)
            continue
            
    return {"cannot_answer": True, "reason": "All AI providers failed or rate-limited. Please wait a moment and try again."}
