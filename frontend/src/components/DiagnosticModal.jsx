export default function DiagnosticModal({ health, onClose }) {
  const DIAG_CMD =
`cd insightflow
backend\\venv\\Scripts\\python.exe -c "
import httpx, os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path('.env'))
key = os.getenv('GROQ_API_KEY','').strip()
print('Key prefix:', key[:12])
r = httpx.post(
  'https://api.groq.com/openai/v1/chat/completions',
  headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
  json={'model':'llama-3.3-70b-versatile','messages':[{'role':'user','content':'hello'}],'max_tokens':5}
)
print(r.status_code, r.text[:300])
"`

  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal">
        <div className="modal-header">
          <h3>System Diagnostics</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div>
          <div className="diag-row">
            <span className="diag-key">API Server</span>
            <span className={`diag-val ${health ? 'ok' : 'fail'}`}>
              {health ? '✓ Running' : '✗ Unreachable — is start.py running?'}
            </span>
          </div>
          <div className="diag-row">
            <span className="diag-key">LLM Provider</span>
            <span className="diag-val ok">Groq (llama-3.3-70b-versatile)</span>
          </div>
          <div className="diag-row">
            <span className="diag-key">Groq API Key</span>
            <span className={`diag-val ${health?.groq_key_looks_valid ? 'ok' : 'fail'}`}>
              {health?.groq_key_looks_valid
                ? `✓ Loaded (${health.groq_key_prefix})`
                : '✗ Not set — add GROQ_API_KEY to .env'}
            </span>
          </div>
          <div className="diag-row">
            <span className="diag-key">Model</span>
            <span className="diag-val">{health?.groq_model || 'llama-3.3-70b-versatile'}</span>
          </div>
          <div className="diag-row">
            <span className="diag-key">GFG Dataset</span>
            <span className={`diag-val ${health?.gfg_dataset_exists ? 'ok' : 'fail'}`}>
              {health?.gfg_dataset_exists
                ? '✓ Found in data/'
                : '✗ Missing — place CSV in data/ folder'}
            </span>
          </div>
        </div>

        {!health?.groq_key_looks_valid && (
          <div style={{
            marginTop: 14, padding: '10px 14px',
            background: 'var(--danger-bg)', borderRadius: 'var(--radius)',
            fontSize: '0.8rem', color: 'var(--danger)', border: '1px solid #fca5a5',
            lineHeight: 1.6,
          }}>
            <strong>Fix:</strong> Get a free key at{' '}
            <a href="https://console.groq.com" target="_blank" rel="noreferrer">console.groq.com</a>
            {' '}→ API Keys → Create Key<br />
            Then add to <code style={{ fontFamily: 'var(--font-mono)' }}>.env</code>:<br />
            <code style={{ fontFamily: 'var(--font-mono)' }}>GROQ_API_KEY=gsk_your_key_here</code>
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: '0.775rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
            TEST GROQ DIRECTLY (run from insightflow/ folder):
          </div>
          <pre className="diag-cmd">{DIAG_CMD}</pre>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 6 }}>
            Or open{' '}
            <a href="http://localhost:8000/debug-llm" target="_blank" rel="noreferrer">
              http://localhost:8000/debug-llm
            </a>
            {' '}in your browser.
            Check terminal for <code style={{ fontFamily: 'var(--font-mono)' }}>[LLM]</code> lines after each query.
          </div>
        </div>
      </div>
    </div>
  )
}