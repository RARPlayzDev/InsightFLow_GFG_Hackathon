import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadCsv, preloadDataset, getSchema } from '../utils/api'

const ROLE_COLORS = {
  continuous: '#3b82f6', score: '#8b5cf6', measure: '#f59e0b',
  dimension: '#10b981', id: '#6b7280', datetime: '#ef4444', text: '#94a3b8',
}

export default function Upload() {
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [schema, setSchema] = useState(null)   // full schema from /schema endpoint
  const inputRef = useRef(null)
  const navigate = useNavigate()

  async function processFile(file) {
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Only CSV files are accepted (.csv extension required)')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setError('File exceeds the 5 MB limit. Please use a smaller dataset.')
      return
    }
    if (file.size === 0) {
      setError('The selected file is empty.')
      return
    }

    // Clear cached dashboard state so new dataset gets a fresh overview
    try {
      ['insightflow_last_result','insightflow_last_prompt',
       'insightflow_last_query','insightflow_overview'].forEach(k => sessionStorage.removeItem(k))
    } catch {}

    setLoading(true)
    setError(null)
    setSchema(null)

    try {
      // Upload and ingest the CSV
      await uploadCsv(file)
      // Fetch full schema (column roles, nunique, samples) for the preview table
      const s = await getSchema()
      setSchema(s)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function useSampleDataset() {
    setLoading(true)
    setError(null)
    setSchema(null)
    try {
      await preloadDataset()
      const s = await getSchema()
      setSchema(s)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) processFile(file)
  }

  function reset() {
    setSchema(null)
    setError(null)
  }

  return (
    <div className="upload-page">
      <h1>Upload Dataset</h1>
      <p className="page-sub">
        Upload any CSV file (up to 5 MB) to start asking natural-language questions about your data.
        Column types are detected automatically.
      </p>

      {!schema ? (
        <>
          {/* Drop zone */}
          <div
            className={`drop-zone ${dragging ? 'drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
          >
            <div className="drop-zone-icon">{loading ? '⏳' : '📁'}</div>
            <h3>{loading ? 'Processing…' : 'Drop your CSV file here'}</h3>
            {!loading && (
              <>
                <p>or click to browse · UTF-8 or latin-1 · max 5 MB</p>
                <button
                  className="btn btn-secondary"
                  disabled={loading}
                  onClick={e => { e.stopPropagation(); inputRef.current?.click() }}
                >
                  Browse files
                </button>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".csv"
              onChange={e => { const f = e.target.files[0]; if (f) processFile(f) }}
            />
          </div>

          <div style={{ textAlign: 'center', margin: '20px 0', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            — or use the pre-loaded dataset —
          </div>

          <div style={{ textAlign: 'center' }}>
            <button
              className="btn btn-secondary btn-lg"
              onClick={useSampleDataset}
              disabled={loading}
            >
              📊 Use GFG Dataset (11,789 rows · 25 columns)
            </button>
          </div>

          {error && (
            <div style={{
              marginTop: 20, padding: '12px 16px',
              background: 'var(--danger-bg)', border: '1px solid #fca5a5',
              borderRadius: 'var(--radius)', color: 'var(--danger)', fontSize: '0.825rem',
            }}>
              <strong>Error:</strong> {error}
            </div>
          )}
        </>
      ) : (
        /* ── Schema preview ── */
        <div className="fade-in">
          <div className="card" style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.975rem' }}>{schema.dataset_name}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
                  {schema.row_count.toLocaleString()} rows · {schema.columns.length} columns
                  {!schema.has_date_column && (
                    <span style={{ marginLeft: 8, color: 'var(--warning)' }}>
                      ⚠ No date column (time-series queries will be declined)
                    </span>
                  )}
                </div>
              </div>
              <span className="badge badge-green">✓ Loaded</span>
            </div>

            {/* Full column preview — populated from /schema */}
            <div style={{ overflowX: 'auto' }}>
              <table className="col-preview-table">
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Type</th>
                    <th>Role</th>
                    <th>Unique</th>
                    <th>Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {schema.columns.map(col => (
                    <tr key={col.safe_name}>
                      <td className="col-name">
                        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{
                            width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                            background: ROLE_COLORS[col.role] || '#94a3b8',
                            display: 'inline-block',
                          }} />
                          {col.safe_name}
                          {col.is_ambiguous && (
                            <span title="Ambiguous — see data dictionary" style={{ color: 'var(--warning)' }}>⚠</span>
                          )}
                        </span>
                      </td>
                      <td>{col.sql_type}</td>
                      <td>
                        <span className={`badge badge-${
                          col.role === 'continuous' ? 'blue'
                          : col.role === 'dimension' ? 'green'
                          : col.role === 'score' ? 'purple'
                          : 'gray'
                        }`}>
                          {col.role}
                        </span>
                      </td>
                      <td>{col.nunique}</td>
                      <td style={{ color: 'var(--text-muted)' }}>
                        {col.samples?.slice(0, 3).join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <button className="btn btn-primary btn-lg" onClick={() => navigate('/dashboard')}>
              Open Dashboard →
            </button>
            <button className="btn btn-secondary" onClick={reset}>
              Upload different file
            </button>
          </div>
        </div>
      )}
    </div>
  )
}