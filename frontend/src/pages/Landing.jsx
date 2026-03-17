import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { preloadDataset } from '../utils/api'

// ── Typewriter effect for the terminal ────────────────────────────────────────
function useTypewriter(text, speed = 28, startDelay = 0) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone]           = useState(false)
  useEffect(() => {
    setDisplayed('')
    setDone(false)
    let i = 0
    const timeout = setTimeout(() => {
      const interval = setInterval(() => {
        i++
        setDisplayed(text.slice(0, i))
        if (i >= text.length) { clearInterval(interval); setDone(true) }
      }, speed)
      return () => clearInterval(interval)
    }, startDelay)
    return () => clearTimeout(timeout)
  }, [text, speed, startDelay])
  return { displayed, done }
}

// ── Animated terminal / demo panel ────────────────────────────────────────────
const TERMINAL_STEPS = [
  { type: 'input',  text: 'Show customer distribution by shopping preference and city tier',  delay: 400  },
  { type: 'step',   text: '→ Building SQL query…',                                            delay: 1600 },
  { type: 'sql',    text: 'SELECT "shopping_preference", "city_tier", COUNT(*) as "count"\nFROM customer_behaviour\nGROUP BY "shopping_preference", "city_tier"\nORDER BY "count" DESC',  delay: 2200 },
  { type: 'step',   text: '→ Executing on SQLite…',                                           delay: 4000 },
  { type: 'result', text: '✓ 9 rows returned  ·  grouped_bar chart  ·  post-processed',       delay: 4600 },
  { type: 'step',   text: '→ Rendering dashboard…',                                           delay: 5200 },
]

function TerminalDemo() {
  const [visibleSteps, setVisibleSteps] = useState([])
  const [chartVisible, setChartVisible] = useState(false)
  const [cycle, setCycle]               = useState(0)
  const containerRef = useRef(null)

  useEffect(() => {
    setVisibleSteps([])
    setChartVisible(false)
    let timers = []
    TERMINAL_STEPS.forEach((step, i) => {
      timers.push(setTimeout(() => {
        setVisibleSteps(prev => [...prev, step])
        if (containerRef.current) {
          containerRef.current.scrollTop = containerRef.current.scrollHeight
        }
      }, step.delay))
    })
    timers.push(setTimeout(() => setChartVisible(true), 6000))
    // Loop
    timers.push(setTimeout(() => setCycle(c => c + 1), 9500))
    return () => timers.forEach(clearTimeout)
  }, [cycle])

  return (
    <div className="lp-terminal-wrap">
      {/* Terminal */}
      <div className="lp-terminal" ref={containerRef}>
        <div className="lp-terminal-bar">
          <span className="lp-dot lp-dot-r"/><span className="lp-dot lp-dot-y"/><span className="lp-dot lp-dot-g"/>
          <span className="lp-terminal-title">InsightFlow · pipeline</span>
        </div>
        <div className="lp-terminal-body">
          {visibleSteps.map((step, i) => (
            <div key={i} className={`lp-line lp-line-${step.type}`}>
              {step.type === 'input' && (
                <><span className="lp-prompt">$</span>
                <span className="lp-input-text">"{step.text}"</span></>
              )}
              {step.type === 'step'   && <span className="lp-step-text">{step.text}</span>}
              {step.type === 'sql'    && (
                <pre className="lp-sql">{step.text}</pre>
              )}
              {step.type === 'result' && <span className="lp-result-text">{step.text}</span>}
            </div>
          ))}
          {visibleSteps.length > 0 && !chartVisible && (
            <span className="lp-cursor">▋</span>
          )}
        </div>
      </div>

      {/* Mini chart preview */}
      <div className={`lp-chart-preview ${chartVisible ? 'lp-chart-visible' : ''}`}>
        <div className="lp-chart-header">
          <span className="lp-chart-title">Customer distribution by shopping preference × city tier</span>
          <span className="lp-badge">grouped_bar</span>
          <span className="lp-badge lp-badge-green">9 rows</span>
        </div>
        <div className="lp-bars">
          {[
            { label: 'Store',  t1: 72, t2: 48, t3: 65 },
            { label: 'Online', t1: 18, t2: 12, t3: 10 },
            { label: 'Hybrid', t1:  8,  t2:  5, t3:  4 },
          ].map(d => (
            <div key={d.label} className="lp-bar-row">
              <span className="lp-bar-label">{d.label}</span>
              <div className="lp-bar-group">
                <div className="lp-bar lp-bar-1" style={{ width: `${d.t1}%` }}/>
                <div className="lp-bar lp-bar-2" style={{ width: `${d.t2}%` }}/>
                <div className="lp-bar lp-bar-3" style={{ width: `${d.t3}%` }}/>
              </div>
            </div>
          ))}
        </div>
        <div className="lp-chart-legend">
          <span className="lp-leg lp-leg-1"/>Tier 1
          <span className="lp-leg lp-leg-2"/>Tier 2
          <span className="lp-leg lp-leg-3"/>Tier 3
        </div>
        <div className="lp-insight">
          ✦ Store preference dominates across all city tiers (70–80%). Hybrid shopping is consistently rare (&lt;10%).
        </div>
      </div>
    </div>
  )
}

// ── Architecture pill strip ────────────────────────────────────────────────────
const STACK = [
  { name: 'FastAPI',       role: 'REST API',         color: '#059669' },
  { name: 'SQLite + WAL',  role: 'Query engine',     color: '#0891b2' },
  { name: 'Groq LLM',      role: 'llama-3.3-70b',    color: '#7c3aed' },
  { name: 'Post-processor','role': '8-rule validator','color': '#d97706' },
  { name: 'React 18',      role: 'Frontend',         color: '#1a56db' },
  { name: 'Recharts',      role: 'Visualisation',    color: '#be185d' },
]

// ── Stat counters ─────────────────────────────────────────────────────────────
const STATS = [
  { value: '11,789', label: 'customer records' },
  { value: '25',     label: 'columns auto-classified' },
  { value: '8',      label: 'post-processing rules' },
  { value: '<1s',    label: 'Groq response time' },
]

// ── Differentiators ───────────────────────────────────────────────────────────
const DIFFS = [
  {
    tag: 'Honesty by design',
    title: 'Refuses to hallucinate',
    body: 'When a question cannot be answered with the available data, InsightFlow says so. No fabricated charts, no confident-looking lies. Most BI tools don\'t do this.',
    color: '#7c3aed',
  },
  {
    tag: 'Post-processor',
    title: 'Auto-corrects chart types',
    body: '8 validation rules run after every LLM response. Pie charts with a dominant 87% slice are automatically converted to bar charts with an explanation badge.',
    color: '#0891b2',
  },
  {
    tag: 'Alias system',
    title: 'Zero hallucinated columns',
    body: 'Every continuous column gets a standardised SQL alias in the schema context. The LLM is told exactly what to write — eliminating the "age_bucket" class of errors.',
    color: '#059669',
  },
  {
    tag: 'Read-only SQLite',
    title: 'Structurally secure',
    body: 'DROP, INSERT, UPDATE, DELETE, ATTACH, PRAGMA are blocklisted by regex. The database opens in ?mode=ro URI. No amount of prompt injection can write data.',
    color: '#d97706',
  },
]

// ── Main component ─────────────────────────────────────────────────────────────
export default function Landing() {
  const navigate   = useNavigate()
  const [loading, setLoading] = useState(false)

  async function launchDemo(query) {
    setLoading(true)
    try {
      await preloadDataset()
    } catch { /* best effort — dashboard handles no-dataset gracefully */ }
    navigate('/dashboard', { state: { initialQuery: query } })
  }

  function goToDashboard() {
    navigate('/dashboard')
  }

  return (
    <div className="lp-page">

      {/* ══ HERO ════════════════════════════════════════════════════════════════ */}
      <section className="lp-hero">
        <div className="lp-hero-inner">
          <div className="lp-hero-left">
            <div className="lp-eyebrow">
              <span className="lp-eyebrow-dot"/>
              GFG Classroom × MVSR Hackathon 2026
            </div>
            <h1 className="lp-h1">
              Plain English<br/>
              <span className="lp-h1-accent">→ Instant Dashboard</span>
            </h1>
            <p className="lp-hero-body">
              Type a business question. InsightFlow generates SQL, validates it, picks the right chart type, and renders an interactive BI dashboard — in under two seconds.
            </p>
            <div className="lp-hero-actions">
              <button className="lp-btn-primary" onClick={() => launchDemo('Show customer distribution by shopping preference and city tier')} disabled={loading}>
                {loading ? 'Loading…' : 'Try live demo →'}
              </button>
              <button className="lp-btn-ghost" onClick={() => navigate('/upload')}>
                Upload your CSV
              </button>
            </div>
            <div className="lp-stats">
              {STATS.map(s => (
                <div key={s.label} className="lp-stat">
                  <span className="lp-stat-val">{s.value}</span>
                  <span className="lp-stat-label">{s.label}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="lp-hero-right">
            <TerminalDemo />
          </div>
        </div>
      </section>

      {/* ══ STACK STRIP ════════════════════════════════════════════════════════ */}
      <section className="lp-stack-strip">
        <span className="lp-stack-label">Built with</span>
        {STACK.map(s => (
          <div key={s.name} className="lp-stack-pill" style={{ '--pill-color': s.color }}>
            <span className="lp-stack-dot"/>
            <span className="lp-stack-name">{s.name}</span>
            <span className="lp-stack-role">{s.role}</span>
          </div>
        ))}
      </section>

      {/* ══ DIFFERENTIATORS ════════════════════════════════════════════════════ */}
      <section className="lp-diffs">
        <div className="lp-section-head">
          <h2 className="lp-h2">What separates InsightFlow from a demo project</h2>
          <p className="lp-section-sub">Every feature below was designed to address a real failure mode in AI-powered BI tools.</p>
        </div>
        <div className="lp-diffs-grid">
          {DIFFS.map(d => (
            <div key={d.title} className="lp-diff-card" style={{ '--diff-color': d.color }}>
              <div className="lp-diff-tag">{d.tag}</div>
              <h3 className="lp-diff-title">{d.title}</h3>
              <p className="lp-diff-body">{d.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ══ PIPELINE ═══════════════════════════════════════════════════════════ */}
      <section className="lp-pipeline">
        <div className="lp-section-head">
          <h2 className="lp-h2">The full pipeline</h2>
          <p className="lp-section-sub">Every query passes through 6 validated stages before a chart renders.</p>
        </div>
        <div className="lp-pipe-steps">
          {[
            { n: '01', title: 'Schema context',   body: 'Column roles, bucket SQL, aliases, and GFG-specific notes injected into every prompt.' },
            { n: '02', title: 'LLM call (Groq)',   body: 'llama-3.3-70b generates SQL + chart spec JSON. System prompt forces raw JSON only.' },
            { n: '03', title: 'SQL validation',    body: 'Blocklist check + word-boundary regex + table name verification before execution.' },
            { n: '04', title: 'SQLite execution',  body: 'Read-only URI mode. Per-session WAL database. Results returned as typed dicts.' },
            { n: '05', title: 'Post-processor',    body: '8 rules: empty guard, row limit, pie correction, pivot, Pearson r, ambiguity flag.' },
            { n: '06', title: 'Cannot-answer gate','body': 'x_col validity, time-series detection, empty chart guard. Honest refusals, not hallucinations.' },
          ].map((s, i) => (
            <div key={s.n} className="lp-pipe-step">
              <div className="lp-pipe-num">{s.n}</div>
              <div className="lp-pipe-content">
                <div className="lp-pipe-title">{s.title}</div>
                <div className="lp-pipe-body">{s.body}</div>
              </div>
              {i < 5 && <div className="lp-pipe-arrow">→</div>}
            </div>
          ))}
        </div>
      </section>

      {/* ══ DEMO QUERIES ═══════════════════════════════════════════════════════ */}
      <section className="lp-demos">
        <div className="lp-section-head">
          <h2 className="lp-h2">Click to run on the live dataset</h2>
          <p className="lp-section-sub">Pre-loaded: 11,789 customers · 25 columns · retail consumer behaviour</p>
        </div>
        <div className="lp-demos-grid">
          {[
            { q: 'Show customer distribution by shopping preference and city tier',         tag: 'grouped_bar · 9 rows',    icon: '▦' },
            { q: 'Compare average online vs store spending by gender and city tier',        tag: 'grouped_bar · 6 rows',    icon: '▦' },
            { q: 'Show age distribution of customers by shopping preference',              tag: 'bar · age_group alias',   icon: '▤' },
            { q: 'Show distribution of daily internet hours by city tier',                    tag: 'bar · bucket SQL',        icon: '▤' },
            { q: 'Compare brand loyalty scores across shopping preferences',               tag: 'bar · AVG score',         icon: '▤' },
            { q: 'Show monthly online orders vs store visits by city tier',                tag: 'grouped_bar · counts',    icon: '▦' },
          ].map(d => (
            <button key={d.q} className="lp-demo-btn" onClick={() => launchDemo(d.q)} disabled={loading}>
              <span className="lp-demo-icon">{d.icon}</span>
              <span className="lp-demo-q">"{d.q}"</span>
              <span className="lp-demo-tag">{d.tag} →</span>
            </button>
          ))}
        </div>
      </section>

      {/* ══ FOOTER CTA ═════════════════════════════════════════════════════════ */}
      <section className="lp-footer-cta">
        <h2 className="lp-h2" style={{ color: '#fff' }}>Ready to explore the data?</h2>
        <p style={{ color: 'rgba(255,255,255,0.7)', marginBottom: 28, fontSize: '1rem' }}>
          No setup required. The dataset is pre-loaded. Ask your first question in seconds.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button className="lp-btn-white" onClick={() => launchDemo('Show customer distribution by shopping preference and city tier')} disabled={loading}>
            {loading ? 'Loading…' : 'Open live dashboard →'}
          </button>
          <button className="lp-btn-ghost-white" onClick={() => navigate('/upload')}>
            Upload your own CSV
          </button>
        </div>
      </section>

      <footer className="lp-footer">
        InsightFlow · Built for GFG Classroom × MVSR Hyderabad Hackathon 2026
      </footer>
    </div>
  )
}