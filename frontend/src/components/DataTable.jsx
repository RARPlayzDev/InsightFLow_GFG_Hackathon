import { useState, useEffect } from 'react'
import { getSessionId } from '../utils/session'

export default function DataTable() {
  const [data, setData] = useState({ headers: [], rows: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function fetchPreview() {
      try {
        const res = await fetch('/api/data-preview', {
          headers: { 'X-Session-ID': getSessionId() }
        })
        if (!res.ok) throw new Error('Failed to load raw data')
        const json = await res.json()
        setData({ headers: json.headers, rows: json.rows })
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    fetchPreview()
  }, [])

  if (loading) return <div className="card" style={{ padding: 40, textAlign: 'center' }}>Loading dataset preview...</div>
  if (error) return <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--danger)' }}>{error}</div>

  if (data.rows.length === 0) {
    return <div className="card" style={{ padding: 40, textAlign: 'center' }}>No data available.</div>
  }

  return (
    <div className="card data-table-wrapper" style={{ overflowX: 'auto', maxHeight: '600px', padding: 0 }}>
      <table className="data-table">
        <thead style={{ position: 'sticky', top: 0, background: 'var(--surface-2)', zIndex: 1 }}>
          <tr>
            {data.headers.map((h, i) => (
              <th key={i} style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid var(--border)', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid var(--border-light)' }}>
              {data.headers.map(h => (
                <td key={h} style={{ padding: '10px 16px', fontSize: '0.85rem', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
                  {row[h] === null ? <span style={{ color: 'var(--text-muted)' }}>NULL</span> : String(row[h])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ padding: '12px 16px', background: 'var(--surface-2)', fontSize: '0.8rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}>
        Showing top 100 rows
      </div>
    </div>
  )
}
