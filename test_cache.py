import sys
import os
import json
import time

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from llm_providers import _RESPONSE_CACHE, _save_cache, _load_cache, _CACHE_FILE

print(f"Testing cache at: {_CACHE_FILE}")

# 1. Test saving
test_res = {"answer": "persistent works"}
_RESPONSE_CACHE["test-key-123"] = [test_res, time.time()]
_save_cache()
print(f"CHECK: Cache file exists? {os.path.exists(_CACHE_FILE)}")

# 2. Test loading
_RESPONSE_CACHE.clear()
_load_cache()
print(f"CHECK: Cache loaded key? {'test-key-123' in _RESPONSE_CACHE}")
if 'test-key-123' in _RESPONSE_CACHE:
    print(f"CHECK: Cache data match? {_RESPONSE_CACHE['test-key-123'][0] == test_res}")

# Cleanup test key
if 'test-key-123' in _RESPONSE_CACHE:
    del _RESPONSE_CACHE['test-key-123']
    _save_cache()
