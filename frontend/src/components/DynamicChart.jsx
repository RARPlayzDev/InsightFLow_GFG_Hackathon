import {
  BarChart, Bar, LineChart, Line, AreaChart, Area,
  PieChart, Pie, Cell, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'

const PALETTE = [
  '#1a56db', '#7c3aed', '#059669', '#d97706',
  '#dc2626', '#0891b2', '#4f46e5', '#be185d',
]

const TICK      = { fontSize: 11, fill: '#6b7280', fontFamily: 'Plus Jakarta Sans, sans-serif' }
const AXIS_LABEL = { fontSize: 11, fill: '#9ca3af', fontFamily: 'Plus Jakarta Sans, sans-serif' }
const TIP = {
  backgroundColor: '#fff', border: '1px solid #dde2ed',
  borderRadius: 6, fontSize: 12, fontFamily: 'Plus Jakarta Sans, sans-serif',
  boxShadow: '0 3px 12px rgba(0,0,0,0.08)',
}

// Convert snake_case or camelCase column names to readable labels
function fmtLabel(col) {
  if (!col) return ''
  return col
    .replace(/_/g, ' ')
    .replace(/\b(avg|avgs)\b/gi, 'Avg')
    .replace(/\b(count)\b/gi, 'Count')
    .replace(/\b(id)\b/gi, 'ID')
    .replace(/\b(sql)\b/gi, 'SQL')
    .replace(/\b(\w)/g, c => c.toUpperCase())
    .trim()
}

function clip(str, n = 14) {
  if (str == null) return ''
  const s = String(str)
  return s.length > n ? s.slice(0, n) + '…' : s
}

function firstKey(row, exclude) {
  return Object.keys(row || {}).find(k => k !== exclude) || ''
}

function resolveYCols(yCols, rows, xCol) {
  if (Array.isArray(yCols) && yCols.length > 0) return yCols
  if (!rows || rows.length === 0) return []
  return Object.keys(rows[0]).filter(k => k !== xCol)
}

// Y-axis label rendered vertically on the left
function yLabel(text) {
  return {
    value: fmtLabel(text),
    angle: -90,
    position: 'insideLeft',
    offset: 14,
    style: { ...AXIS_LABEL, textAnchor: 'middle' },
  }
}

// X-axis label below the axis
function xLabel(text) {
  return {
    value: fmtLabel(text),
    position: 'insideBottom',
    offset: -4,
    style: AXIS_LABEL,
  }
}

export default function DynamicChart({ type, rows, xCol, yCols }) {
  if (!rows || !Array.isArray(rows) || rows.length === 0)
    return <div className="chart-warning">No data to display.</div>
  if (!xCol)
    return <div className="chart-warning">Chart configuration error: no x-axis column specified.</div>

  const safeYCols = resolveYCols(yCols, rows, xCol)
  const H = 280  // slightly taller to fit axis labels

  // ── PIE ──────────────────────────────────────────────────────────────────────
  if (type === 'pie') {
    const yKey = safeYCols[0]
    if (!yKey) return <div className="chart-warning">Pie chart needs a value column.</div>
    const data = rows.map(r => ({
      name:  r[xCol] != null ? String(r[xCol]) : '—',
      value: Number(r[yKey] ?? 0),
    }))
    return (
      <>
        <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: 6, textAlign: 'center' }}>
          {fmtLabel(xCol)} — {fmtLabel(yKey)}
        </div>
        <ResponsiveContainer width="100%" height={H}>
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name"
              cx="50%" cy="50%" outerRadius={96} isAnimationActive={false}
              label={({ name, percent }) => `${clip(name)} ${(percent * 100).toFixed(0)}%`}
              labelLine={{ stroke: '#dde2ed' }}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Pie>
            <Tooltip contentStyle={TIP} formatter={(val) => [val.toLocaleString(), fmtLabel(yKey)]} />
            <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ResponsiveContainer>
      </>
    )
  }

  // ── SCATTER ──────────────────────────────────────────────────────────────────
  if (type === 'scatter') {
    const yKey = safeYCols[0]
    if (!yKey) return <div className="chart-warning">Scatter chart needs a y-axis column.</div>
    const data = rows
      .map(r => ({ x: Number(r[xCol] ?? 0), y: Number(r[yKey] ?? 0) }))
      .filter(p => !isNaN(p.x) && !isNaN(p.y))
    if (data.length === 0)
      return <div className="chart-warning">No numeric data for scatter chart.</div>
    return (
      <ResponsiveContainer width="100%" height={H}>
        <ScatterChart margin={{ top: 10, right: 16, bottom: 36, left: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eaecf4" />
          <XAxis dataKey="x" type="number" name={xCol} tick={TICK}
            label={xLabel(xCol)} />
          <YAxis dataKey="y" type="number" name={yKey} tick={TICK}
            width={64} label={yLabel(yKey)} />
          <Tooltip contentStyle={TIP} cursor={{ strokeDasharray: '3 3' }}
            formatter={(val, name) => [val.toLocaleString(), fmtLabel(name)]} />
          <Scatter data={data} fill={PALETTE[0]} fillOpacity={0.7} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  // ── GROUPED BAR ───────────────────────────────────────────────────────────────
  if (type === 'grouped_bar') {
    const bars = safeYCols.length > 0
      ? safeYCols
      : Object.keys(rows[0] || {}).filter(k => k !== xCol)
    if (bars.length === 0)
      return <div className="chart-warning">No series columns for grouped bar.</div>
    // Y-axis label: shared metric name if all bars share a common root (e.g. all "count"), else "value"
    const yAxisLabel = bars.length === 1 ? bars[0]
      : bars.every(b => b.includes('count') || b.includes('Count')) ? 'count'
      : bars.every(b => b.includes('spend') || b.includes('Spend')) ? 'avg spend'
      : bars.every(b => b.includes('score') || b.includes('Score')) ? 'score'
      : bars.every(b => b.includes('order') || b.includes('visit')) ? 'count'
      : 'value'
    return (
      <ResponsiveContainer width="100%" height={H}>
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 36, left: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eaecf4" vertical={false} />
          <XAxis dataKey={xCol} tick={{ ...TICK, dy: 6 }}
            tickFormatter={v => clip(String(v ?? ''), 12)}
            label={xLabel(xCol)} />
          <YAxis tick={TICK} width={64} label={yLabel(yAxisLabel)} />
          <Tooltip contentStyle={TIP}
            formatter={(val, name) => [
              typeof val === 'number' ? val.toLocaleString() : val,
              fmtLabel(name)
            ]} />
          <Legend iconSize={10} wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
            formatter={fmtLabel} />
          {bars.map((key, i) => (
            <Bar key={key} dataKey={key} fill={PALETTE[i % PALETTE.length]}
              radius={[3, 3, 0, 0]} maxBarSize={40} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  // ── BAR ───────────────────────────────────────────────────────────────────────
  if (type === 'bar') {
    const yKey = safeYCols[0] || firstKey(rows[0], xCol)
    if (!yKey) return <div className="chart-warning">Bar chart needs a value column.</div>
    return (
      <ResponsiveContainer width="100%" height={H}>
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 36, left: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eaecf4" vertical={false} />
          <XAxis dataKey={xCol} tick={{ ...TICK, dy: 6 }}
            tickFormatter={v => clip(String(v ?? ''), 14)}
            label={xLabel(xCol)} />
          <YAxis tick={TICK} width={64} label={yLabel(yKey)} />
          <Tooltip contentStyle={TIP}
            formatter={(val) => [
              typeof val === 'number' ? val.toLocaleString() : val,
              fmtLabel(yKey)
            ]} />
          <Bar dataKey={yKey} fill={PALETTE[0]} radius={[3, 3, 0, 0]}
            maxBarSize={44} isAnimationActive={false}>
            {rows.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  // ── LINE ─────────────────────────────────────────────────────────────────────
  if (type === 'line') {
    const lineKeys = safeYCols.length > 0
      ? safeYCols
      : [firstKey(rows[0], xCol)].filter(Boolean)
    if (lineKeys.length === 0)
      return <div className="chart-warning">Line chart needs a value column.</div>
    const yAxisLabel = lineKeys.length === 1 ? lineKeys[0] : 'value'
    return (
      <ResponsiveContainer width="100%" height={H}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 36, left: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eaecf4" />
          <XAxis dataKey={xCol} tick={{ ...TICK, dy: 6 }}
            tickFormatter={v => clip(String(v ?? ''), 12)}
            label={xLabel(xCol)} />
          <YAxis tick={TICK} width={64} label={yLabel(yAxisLabel)} />
          <Tooltip contentStyle={TIP}
            formatter={(val, name) => [
              typeof val === 'number' ? val.toLocaleString() : val,
              fmtLabel(name)
            ]} />
          {lineKeys.length > 1 && (
            <Legend iconSize={10} wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
              formatter={fmtLabel} />
          )}
          {lineKeys.map((key, i) => {
            const isForecast = key.endsWith('_forecast')
            return (
              <Line key={key} type="monotone" dataKey={key}
                stroke={isForecast ? '#94a3b8' : PALETTE[i % PALETTE.length]} 
                strokeWidth={isForecast ? 2 : 2.5}
                strokeDasharray={isForecast ? "5 5" : undefined}
                dot={isForecast ? false : { r: 3, fill: PALETTE[i % PALETTE.length] }}
                activeDot={{ r: 5 }} isAnimationActive={false} />
            )
          })}
        </LineChart>
      </ResponsiveContainer>
    )
  }

  // ── AREA ─────────────────────────────────────────────────────────────────────
  if (type === 'area') {
    const yKey = safeYCols[0] || firstKey(rows[0], xCol)
    if (!yKey) return <div className="chart-warning">Area chart needs a value column.</div>
    return (
      <ResponsiveContainer width="100%" height={H}>
        <AreaChart data={rows} margin={{ top: 8, right: 16, bottom: 36, left: 16 }}>
          <defs>
            <linearGradient id="areaGrad0" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={PALETTE[0]} stopOpacity={0.18} />
              <stop offset="95%" stopColor={PALETTE[0]} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#eaecf4" />
          <XAxis dataKey={xCol} tick={{ ...TICK, dy: 6 }} label={xLabel(xCol)} />
          <YAxis tick={TICK} width={64} label={yLabel(yKey)} />
          <Tooltip contentStyle={TIP}
            formatter={(val) => [
              typeof val === 'number' ? val.toLocaleString() : val,
              fmtLabel(yKey)
            ]} />
          <Area type="monotone" dataKey={yKey} stroke={PALETTE[0]} strokeWidth={2.5}
            fill="url(#areaGrad0)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  return (
    <div className="chart-warning">
      Unknown chart type: <code style={{ fontFamily: 'var(--font-mono)' }}>{type}</code>.
    </div>
  )
}