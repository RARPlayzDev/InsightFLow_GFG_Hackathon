import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getHistory, clearHistory } from '../utils/api'

const CHART_TYPE_ICONS = {
  bar: '▦', grouped_bar: '▦▦', line: '∿', area: '◿', pie: '◑', scatter: '⁘'
}

function timeAgo(ts) {
  const diff = (Date.now() / 1000) - ts
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(ts * 1000).toLocaleDateString()
}

export default function History() {
  const [data,     setData]     = useState(null)
  const [error,    setError]    = useState(null)
  const [clearing, setClearing] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    getHistory()
      .then(setData)
      .catch(err => setError(err.message))
  }, [])

  function reloadQuery(prompt) {
    navigate('/dashboard', { state: { initialQuery: prompt } })
  }

  async function handleClear() {
    setClearing(true)
    try {
      await clearHistory()
      setData({ expired: false, items: [] })
    } catch (err) {
      setError(err.message)
    } finally {
      setClearing(false)
    }
  }

  if (error) return (
    <div className="history-page">
      <h1>Query History</h1>
      <div style={{ padding: '16px', background: 'var(--danger-bg)', borderRadius: 'var(--radius)', color: 'var(--danger)', fontSize: '0.825rem' }}>
        <strong>Error:</strong> {error}
      </div>
    </div>
  )

  if (!data) return (
    <div className="history-page">
      <h1>Query History</h1>
      {[1,2,3].map(i => (
        <div key={i} className="skeleton" style={{ height: 80, borderRadius: 12, marginBottom: 12 }} />
      ))}
    </div>
  )

  if (data.expired) return (
    <div className="history-page">
      <h1>Query History</h1>
      <div className="history-empty">
        <div style={{ fontSize: '2rem', marginBottom: 12 }}>⏱</div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>Session expired</div>
        <div style={{ fontSize: '0.825rem', marginBottom: 16 }}>Sessions last 30 minutes. Return to the dashboard to start a new one.</div>
        <button className="btn btn-primary" onClick={() => navigate('/dashboard')}>Go to Dashboard</button>
      </div>
    </div>
  )

  if (!data.items?.length) return (
    <div className="history-page">
      <h1>Query History</h1>
      <p className="page-sub">Your query history for this session.</p>
      <div className="history-empty">
        <div style={{ fontSize: '2rem', marginBottom: 12 }}>📭</div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>No queries yet</div>
        <div style={{ fontSize: '0.825rem', marginBottom: 16 }}>Head to the dashboard and ask your first question.</div>
        <button className="btn btn-primary" onClick={() => navigate('/dashboard')}>Open Dashboard</button>
      </div>
    </div>
  )

  const reversed = [...data.items].reverse()
  return (
    <div className="history-page">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <h1 style={{ margin: 0 }}>Query History</h1>
        <button className="btn btn-secondary btn-sm" onClick={handleClear} disabled={clearing}>
          {clearing ? '…' : '✕ Clear history'}
        </button>
      </div>
      <p className="page-sub">{data.items.length} queries this session</p>

      {reversed.map((item, i) => (
        <div className="history-item" key={`${item.timestamp}-${i}`}>
          <div className="history-item-num">{data.items.length - i}</div>
          <div className="history-item-body">
            <div className="history-prompt">{item.prompt}</div>
            <div className="history-meta">
              <span>{timeAgo(item.timestamp)}</span>
              {item.cannot_answer
                ? <span className="badge badge-yellow">Cannot answer</span>
                : <>
                    {item.chart_specs?.map((c, j) => (
                      <span key={j} className="badge badge-gray">
                        {CHART_TYPE_ICONS[c.type] || '▦'} {c.type}
                      </span>
                    ))}
                    <span className="badge badge-blue">{item.kpi_specs?.length || 0} KPIs</span>
                  </>
              }
            </div>
            {item.insight && !item.cannot_answer && (
              <div className="history-insight">{item.insight}</div>
            )}
            {item.cannot_answer && item.reason && (
              <div className="history-insight" style={{ color: 'var(--warning)' }}>⚠ {item.reason}</div>
            )}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => reloadQuery(item.prompt)} title="Re-run this query">
            ↩ Rerun
          </button>
        </div>
      ))}
    </div>
  )
}