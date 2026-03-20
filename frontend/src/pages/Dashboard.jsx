import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { getSchema, runQuery, runRefine, getOverview, getHistory } from '../utils/api'
import DynamicChart from '../components/DynamicChart'
import ExportButton from '../components/ExportButton'
import DiagnosticModal from '../components/DiagnosticModal'
import DataTable from '../components/DataTable'
import {
  KpiCard, InsightCard, CannotAnswer, ClarificationCard, SqlToggle, ChartSkeleton,
} from '../components/SharedComponents'
import { getSessionId } from '../utils/session'
import ChatBot from '../components/ChatBot'
import FullReportWidget from '../components/FullReportWidget'

const DEMO_CHIPS = [
  'Show customer distribution by shopping preference and city tier',
  'Compare average online vs store spending by gender and city tier',
  'Show age distribution of customers by shopping preference',
]

// ── sessionStorage helpers ─────────────────────────────────────────────────────
// Persist the last result so navigating away and back doesn't wipe the dashboard.
const SS_KEY      = 'insightflow_last_result'
const SS_PROMPT   = 'insightflow_last_prompt'
const SS_QUERY    = 'insightflow_last_query'
const SS_OVERVIEW = 'insightflow_overview'

function ssGet(key) {
  try { const v = sessionStorage.getItem(key); return v ? JSON.parse(v) : null } catch { return null }
}
function ssSet(key, val) {
  try { sessionStorage.setItem(key, JSON.stringify(val)) } catch {}
}
function ssClear() {
  try {
    sessionStorage.removeItem(SS_KEY)
    sessionStorage.removeItem(SS_PROMPT)
    sessionStorage.removeItem(SS_QUERY)
  } catch {}
}

function ssClearAll() {
  try {
    sessionStorage.removeItem(SS_KEY)
    sessionStorage.removeItem(SS_PROMPT)
    sessionStorage.removeItem(SS_QUERY)
    sessionStorage.removeItem(SS_OVERVIEW)
  } catch {}
}

// ── Pipeline progress ──────────────────────────────────────────────────────────
function PipelineProgress() {
  const steps = ['Query received', 'Building SQL', 'Calling Groq AI', 'Executing SQL', 'Rendering charts']
  const [step, setStep] = useState(0)
  useEffect(() => {
    const timings = [300, 800, 2500, 5500]
    const timers  = timings.map((ms, i) => setTimeout(() => setStep(i + 1), ms))
    return () => timers.forEach(clearTimeout)
  }, [])
  return (
    <div className="pipeline-progress">
      <div className="pipeline-label">Processing your query</div>
      <div className="pipeline-steps">
        {steps.map((s, i) => (
          <div key={s} className={`pipeline-step ${i < step ? 'done' : i === step ? 'active' : ''}`}>
            <span className="pipeline-dot" /><span>{s}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Correction badge ───────────────────────────────────────────────────────────
function CorrectionBadge({ chart }) {
  if (!chart._type_corrected) return null
  return (
    <div className="correction-badge">
      ✓ Auto-corrected: pie → bar
      <span className="correction-reason">(one category &gt;60% of total — pie would mislead)</span>
    </div>
  )
}

// ── AI Overview card ───────────────────────────────────────────────────────────
function OverviewCard({ overview, loading }) {
  const [expanded, setExpanded] = useState(false)
  if (loading) return (
    <div className="overview-card">
      <div className="overview-loading">
        <span className="overview-spinner" />
        Analysing dataset with AI…
      </div>
    </div>
  )
  if (!overview) return null
  return (
    <div className="overview-card fade-in">
      <div className="overview-header">
        <div className="overview-icon">✦</div>
        <div>
          <div className="overview-title">AI Dataset Overview</div>
          <div className="overview-summary">{overview.summary}</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => setExpanded(e => !e)}
          style={{ marginLeft: 'auto', flexShrink: 0 }}>
          {expanded ? 'Less ▲' : 'More ▼'}
        </button>
      </div>

      {expanded && (
        <div className="overview-body">
          {overview.expert_note && (
            <div className="overview-expert">
              <span className="overview-expert-label">Expert note</span>
              {overview.expert_note}
            </div>
          )}

          {overview.column_groups?.length > 0 && (
            <div className="overview-groups">
              {overview.column_groups.map((g, i) => (
                <div key={i} className="overview-group">
                  <div className="overview-group-name">{g.group}</div>
                  <div className="overview-group-desc">{g.description}</div>
                  <div className="overview-group-cols">
                    {g.columns?.map(c => (
                      <span key={c} className="badge badge-gray" style={{ fontSize: '0.7rem' }}>{c}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {overview.suggested_questions?.length > 0 && (
            <div className="overview-suggestions">
              <div className="overview-suggestions-label">Try asking:</div>
              {overview.suggested_questions.map((q, i) => (
                <div key={i} className="overview-suggestion-q">→ {q}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main Dashboard ─────────────────────────────────────────────────────────────
export default function Dashboard({ health }) {
  const location = useLocation()

  const [schema,      setSchema]      = useState(null)
  const [loadError,   setLoadError]   = useState(null)
  const [loading,     setLoading]     = useState(false)
  const [query,       setQuery]       = useState(ssGet(SS_QUERY) || '')
  const [result,      setResult]      = useState(ssGet(SS_KEY))
  const [queryError,  setQueryError]  = useState(null)
  const [refineInput, setRefineInput] = useState('')
  const [refining,    setRefining]    = useState(false)
  const [lastPrompt,  setLastPrompt]  = useState(ssGet(SS_PROMPT) || '')
  const [showDiag,    setShowDiag]    = useState(false)
  const [overview,    setOverview]    = useState(ssGet(SS_OVERVIEW))
  const [overviewLoading, setOverviewLoading] = useState(false)
  
  // Dashboard view toggle: 'analytics' | 'data'
  const [viewMode, setViewMode] = useState('analytics')
  const [isSchemaOpen, setIsSchemaOpen] = useState(true)
  
  const [showFullReport, setShowFullReport] = useState(false)
  const [highlightedChartId, setHighlightedChartId] = useState(null)
  const [isInsightsOpen, setIsInsightsOpen] = useState(true)

  const initialQueryFired = useRef(false)



  // ── Load schema (passive — no auto-ingest) ───────────────────────────────────
  // We no longer auto-load the dataset on Dashboard mount. The user must
  // explicitly load a dataset via the Upload page first. This eliminates the
  // startup race condition where preload fails because the server just started.
  // If a session already has a dataset loaded (from Upload or a previous visit),
  // we just fetch the schema cheaply. If not, show the "no dataset" prompt.
  useEffect(() => {
    let cancelled = false
    async function init() {
      setLoadError(null)
      try {
        const s = await getSchema()
        if (cancelled) return
        setSchema(s)
        
        // AUTO-REPORT: If no previous result exists, generate one automatically
        if (!ssGet(SS_KEY) && !cancelled) {
          setLoading(true)
          try {
            const res = await fetch('/api/auto-report', {
              method: 'POST',
              headers: { 'X-Session-ID': getSessionId() }
            })
            if (res.ok) {
              const autoReport = await res.json()
                if (!cancelled) {
                  setResult(autoReport)
                  ssSet(SS_KEY, autoReport)
                  
                  // Extract overview from the auto-report result (1-call optimization)
                  if (autoReport.dataset_overview) {
                    setOverview(autoReport.dataset_overview)
                    ssSet(SS_OVERVIEW, autoReport.dataset_overview)
                  }

                  const firstPrompt = "Auto-Generated Insights"
                  setLastPrompt(firstPrompt)
                  ssSet(SS_PROMPT, firstPrompt)
                }
              }
            } catch { /* fail silently */ }
            finally { if (!cancelled) setLoading(false) }
          }
        } catch (err) {
        // 404 = no dataset loaded yet — this is expected, not an error
        if (!cancelled) {
          if (err.message?.includes('404') || err.message?.includes('Session not found')) {
            setSchema(null)  // show the "load a dataset" prompt cleanly
          } else {
            setLoadError(err.message)
          }
        }
      }
    }
    init()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Fire initial query from Landing exactly once ──────────────────────────────
  useEffect(() => {
    if (!schema || initialQueryFired.current) return
    const iq = location.state?.initialQuery
    if (!iq) return
    initialQueryFired.current = true
    setQuery(iq)
    submitQuery(iq)
  }, [schema]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Query submission ──────────────────────────────────────────────────────────
  // Auto-expand insights on new result
  useEffect(() => {
    if (result?.brief_insights?.length > 0) setIsInsightsOpen(true)
  }, [result])

  async function submitQuery(overridePrompt = null) {
    const text = (typeof overridePrompt === 'string' ? overridePrompt : query).trim()
    if (!text) return
    setLoading(true)
    setResult(null)
    setQueryError(null)
    setLastPrompt(text)
    ssSet(SS_PROMPT, text)
    ssSet(SS_QUERY, text)
    try {
      const res = await runQuery(text)
      setResult(res)
      ssSet(SS_KEY, res)
    } catch (err) {
      setQueryError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Refine ────────────────────────────────────────────────────────────────────
  async function submitRefine() {
    const text = refineInput.trim()
    if (!text) return
    setRefining(true)
    setQueryError(null)
    try {
      const res = await runRefine(text, lastPrompt)
      setResult(res)
      const newPrompt = `${lastPrompt} → ${text}`
      setLastPrompt(newPrompt)
      ssSet(SS_KEY, res)
      ssSet(SS_PROMPT, newPrompt)
      setRefineInput('')
    } catch (err) {
      setQueryError(err.message)
    } finally {
      setRefining(false)
    }
  }

  // ── Flush dashboard ───────────────────────────────────────────────────────────
  function flushDashboard() {
    setResult(null)
    setQuery('')
    setLastPrompt('')
    setQueryError(null)
    setRefineInput('')
    ssClear()
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitQuery() }
  }

  const roleCount = schema
    ? schema.columns.reduce((acc, c) => { acc[c.role] = (acc[c.role] || 0) + 1; return acc }, {})
    : {}

  return (
    <div className="dashboard-layout">

      {/* ══ SIDEBAR ══════════════════════════════════════════════════════════════ */}
      <aside className="sidebar">
        <div className="sidebar-header" onClick={() => setIsSchemaOpen(!isSchemaOpen)} 
          style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', userSelect: 'none' }}>
          <h3 style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-primary)' }}>Data Dictionary</h3>
          <span style={{ fontSize: '0.7rem', opacity: 0.5, transform: isSchemaOpen ? 'none' : 'rotate(-90deg)', transition: 'transform 0.2s' }}>▼</span>
        </div>

        <div className="sidebar-content-area">
          {!schema ? (
            <div style={{ padding: 20 }}>
              {loadError ? (
                <div style={{ fontSize: '0.8rem', color: 'var(--danger)', lineHeight: 1.65 }}>
                  <strong>Error:</strong><br />{loadError}
                </div>
              ) : (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.7 }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
                    No dataset loaded
                  </div>
                  Go to{' '}
                  <a href="/upload" style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 600 }}
                    onClick={e => { e.preventDefault(); window.location.href = '/upload' }}>
                    Upload
                  </a>
                  {' '}to load the GFG dataset or upload your own CSV.
                </div>
              )}
            </div>
          ) : isSchemaOpen ? (
            <>
              <div className="sidebar-meta-area" style={{ padding: '0 16px 16px' }}>
                <div className="dataset-name" style={{ fontWeight: 600, marginBottom: 4 }}>{schema.dataset_name}</div>
                <div className="dataset-meta" style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <span className="meta-pill">{schema.row_count.toLocaleString()} rows</span>
                  <span className="meta-pill">{schema.columns.length} cols</span>
                  {!schema.has_date_column && (
                    <span className="meta-pill warn" title="Time-series queries will be declined">
                      ⚠ No date col
                    </span>
                  )}
                </div>
              </div>

              <div className="sidebar-section">
                <div className="sidebar-section-label">Column Types</div>
                <div className="role-breakdown">
                  {Object.entries(roleCount).map(([role, count]) => (
                    <div className="role-row" key={role}>
                      <div className="role-label-wrap">
                        <div className={`role-dot role-${role}`} />
                        <span style={{ fontSize: '0.79rem' }}>{role}</span>
                      </div>
                      <span className="role-count">{count}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="sidebar-section" style={{ borderBottom: 'none' }}>
                <div className="sidebar-section-label">All Columns</div>
                <div className="col-list">
                  {schema.columns.map(c => (
                    <div className="col-item" key={c.safe_name}
                      title={`${c.original_name} · ${c.role} · ${c.nunique} unique values`}>
                      <div className={`role-dot role-${c.role}`} style={{ flexShrink: 0 }} />
                      <span className="col-item-name">{c.safe_name}</span>
                      {c.is_ambiguous && <span title="Ambiguous" style={{ color: 'var(--warning)' }}>⚠</span>}
                      <span className="col-item-nunique">{c.nunique}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
              Schema hidden. Click header to expand.
            </div>
          )}
        </div>
      </aside>

      {/* ══ MAIN ════════════════════════════════════════════════════════════════ */}
      <div className="dashboard-main">

        {/* Status bar */}
        <div className="status-bar">
          <div className="status-item" onClick={() => setShowDiag(true)}
            title="Click to open diagnostics" style={{ cursor: 'pointer' }}>
            <span className={`status-dot ${health?.groq_key_looks_valid ? '' : 'error'}`} />
            <span>Groq {health?.groq_key_looks_valid ? 'ready' : 'key invalid'}</span>
          </div>
          <div className="status-item">
            <span className={`status-dot ${schema ? '' : 'warn'}`} />
            <span>
              {schema
                ? `Dataset loaded · ${schema.row_count.toLocaleString()} rows · ${schema.columns.length} cols`
                : 'No dataset — go to Upload'}
            </span>
          </div>
          
          {schema && (
            <div className="view-toggle" style={{ marginLeft: 20, display: 'flex', gap: 4, background: 'var(--surface-2)', padding: 4, borderRadius: 'var(--radius)' }}>
              <button 
                className={`btn btn-sm ${viewMode === 'analytics' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('analytics')}
                style={{ margin: 0 }}>Analytics</button>
              <button 
                className={`btn btn-sm ${viewMode === 'data' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('data')}
                style={{ margin: 0 }}>Raw Data</button>
            </div>
          )}

          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            {schema && (
               <button className="btn btn-primary btn-sm" onClick={() => setShowFullReport(true)}
                  title="Generate a comprehensive 4-chart business report autonomously">
                  ✦ Generate Full Report
               </button>
            )}
            {result && viewMode === 'analytics' && (
              <>
                <ExportButton targetId="results-area" prompt={lastPrompt} result={result} />
                <button className="btn btn-ghost btn-sm" onClick={flushDashboard}
                  title="Clear the current dashboard results">
                  ✕ Clear
                </button>
              </>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => setShowDiag(true)}>
              ⚙ Diagnostics
            </button>
          </div>
        </div>

        {viewMode === 'data' ? (
          <div style={{ padding: '0 28px', marginTop: 24 }}>
            <div style={{ marginBottom: 16 }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Raw Dataset Preview</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>A rapid tabular view of your connected data.</p>
            </div>
            <DataTable />
          </div>
        ) : (
          <div className="analytics-view">
            {/* AI Overview */}
            <OverviewCard overview={overview} loading={overviewLoading} />

            {/* AI Brief Insights Dropdown (Top Row) */}
            {result?.brief_insights?.length > 0 && (
              <div className="brief-insights-dropdown card">
                <div className="dropdown-header" onClick={() => setIsInsightsOpen(!isInsightsOpen)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: '1rem' }}>💡</span>
                    <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>AI Brief Insights</span>
                    <span className="badge badge-blue" style={{ fontSize: '0.7rem' }}>{result.brief_insights.length} Notes</span>
                  </div>
                  <span className={`dropdown-arrow ${isInsightsOpen ? 'open' : ''}`}>▼</span>
                </div>
                {isInsightsOpen && (
                  <div className="dropdown-content fade-in">
                    <ul className="brief-insight-list">
                      {result.brief_insights.map((bi, i) => (
                        <li key={i}>{bi}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

        {/* Query input */}


        {/* Results */}
        <div className="results-area">

          {queryError && (
            <div className="cannot-answer fade-in">
              <div className="cannot-answer-icon" style={{ background: 'var(--danger)' }}>✕</div>
              <div>
                <h4>Request failed</h4>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', marginBottom: 6 }}>{queryError}</p>
                <p style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                  Check the terminal for{' '}
                  <code style={{ fontFamily: 'var(--font-mono)' }}>[LLM]</code> log lines,
                  or click ⚙ Diagnostics above.
                </p>
              </div>
            </div>
          )}

          {loading && (
            <div className="fade-in">
              <PipelineProgress />
              <ChartSkeleton count={2} />
            </div>
          )}

          {!loading && result && (
            <div id="results-area" className="fade-in">
              {result.cannot_answer && <CannotAnswer reason={result.reason} />}
              {result.clarification_needed && (
                <ClarificationCard 
                  prompt={result.clarification_prompt} 
                  onUse={(p) => { setQuery(p); submitQuery(p); }} 
                />
              )}

              {result.kpis?.length > 0 && (
                <div className="kpi-grid">
                  {result.kpis.map((k, i) => (
                    <KpiCard key={i} label={k.label} value={k.value} format={k.format} />
                  ))}
                </div>
              )}

              {result.charts?.length > 0 && (
                <div className="chart-grid">
                  {result.charts.map((chart, i) => (
                <div className={`chart-card ${highlightedChartId === i ? 'highlighted' : ''}`} key={i} id={`chart-card-${i}`}>
                      <div className="chart-card-header">
                        <div className="chart-title">{chart.title}</div>
                        <div className="chart-meta">
                          <span className="badge badge-gray">{chart.type}</span>
                          {(chart.raw_row_count ?? chart.rows?.length ?? 0) > 0 && (
                            <span className="badge badge-blue">{chart.raw_row_count ?? chart.rows.length} rows</span>
                          )}
                          {(chart.raw_row_count ?? chart.rows?.length ?? 0) > 0 && (
                            <button
                              className="btn btn-ghost btn-sm"
                              style={{ fontSize: '0.7rem', padding: '2px 8px' }}
                              title="Download chart as PNG"
                              onClick={async () => {
                                try {
                                  const el = document.getElementById(`chart-${i}`)
                                  if (!el) return
                                  const { toPng } = await import('html-to-image')
                                  const url = await toPng(el, { backgroundColor: '#ffffff' })
                                  const a = document.createElement('a')
                                  a.href = url
                                  a.download = `${chart.title.replace(/\s+/g, '_')}.png`
                                  a.click()
                                } catch {}
                              }}
                            >
                              ↓ PNG
                            </button>
                          )}
                        </div>
                      </div>
                      <CorrectionBadge chart={chart} />
                      {chart.note && <div className="chart-note">⚠ {chart.note}</div>}
                      {chart.correlation_note && (
                        <div className="correlation-note">
                          <strong>Correlation:</strong> {chart.correlation_note}
                        </div>
                      )}
                      <div id={`chart-${i}`}>
                        {chart.warning ? (
                          <div className="chart-warning">⚠ {chart.warning}</div>
                        ) : (
                          <DynamicChart
                            type={chart.type} rows={chart.rows}
                            xCol={chart.x_col} yCols={chart.y_cols}
                            colorCol={chart.color_col}
                          />
                        )}
                      </div>
                      <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border-light)' }}>
                        <SqlToggle sql={chart.sql} />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {result.insight && !result.cannot_answer && (
                <InsightCard text={result.insight} />
              )}





              {!result.cannot_answer && result.charts?.length > 0 && (
                <div className="action-bar">
                  <span className="action-bar-label" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span>
                      Query:{' '}
                      <em style={{ color: 'var(--text-secondary)' }}>
                        "{lastPrompt.length > 80 ? lastPrompt.slice(0, 80) + '…' : lastPrompt}"
                      </em>
                    </span>
                    {result.provider && (
                      <span className={`badge ${result.provider === 'gemini' ? 'badge-purple' : 'badge-yellow'}`} title={`Powered by ${result.provider === 'gemini' ? 'Google Gemini' : 'Groq'}`}>
                        {result.provider === 'gemini' ? '🔷 Gemini' : '⚡ Groq'}
                      </span>
                    )}
                  </span>
                  <ExportButton targetId="results-area" prompt={lastPrompt} result={result} />
                </div>
              )}

            </div>
          )}

          {schema && (
            <div className="query-area-bottom">
              <div className="query-input-row">
                <textarea
                  className="query-input"
                  placeholder="Ask a deeper analytical question or prompt the AI..."
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={loading}
                  rows={1}
                />
                <button className="btn btn-primary"
                  onClick={() => submitQuery()}
                  disabled={loading || !query.trim()}>
                  {loading ? '⏳' : '→'} Analyse
                </button>
              </div>

              <div className="suggestion-section">
                <div className="chip-row">
                  {(result?.suggestions || DEMO_CHIPS).map(chip => (
                    <button key={chip}
                      className={`chip ${loading ? 'chip-loading' : ''} ${result?.suggestions ? 'suggestion-chip-active' : ''}`}
                      onClick={() => { setQuery(chip); submitQuery(chip) }}
                      disabled={loading}
                      title={chip}>
                      {chip.length > 54 ? chip.slice(0, 54) + '…' : chip}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {!loading && !result && !queryError && !schema && (
            <div className="empty-state">
              <div className="empty-state-icon">📊</div>
              <h3>No dataset loaded</h3>
              <p>Load a dataset first to start asking questions.</p>
              <a href="/upload"
                onClick={e => { e.preventDefault(); window.location.href = '/upload' }}
                className="btn btn-primary"
                style={{ display: 'inline-block', marginTop: 12 }}>
                Go to Upload →
              </a>
            </div>
          )}
          </div>
          </div>
        )}
        </div>

      {showDiag && <DiagnosticModal health={health} onClose={() => setShowDiag(false)} />}
      {schema && <ChatBot context={result} />}
      {showFullReport && <FullReportWidget onComplete={() => setShowFullReport(false)} />}
    </div>
  )
}