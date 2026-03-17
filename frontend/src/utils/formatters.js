export function formatKpiValue(value, format) {
  if (value === null || value === undefined) return '—'

  if (format === 'text') return String(value)

  const num = Number(value)
  if (isNaN(num)) return String(value)

  if (format === 'currency') {
    if (num >= 1_00_00_000) return '₹' + (num / 1_00_00_000).toFixed(2) + 'Cr'
    if (num >= 1_00_000)    return '₹' + (num / 1_00_000).toFixed(2) + 'L'
    if (num >= 1_000)       return '₹' + (num / 1_000).toFixed(1) + 'K'
    return '₹' + num.toLocaleString('en-IN')
  }

  if (format === 'percentage') return num.toFixed(1) + '%'

  // number
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M'
  if (num >= 1_000)     return (num / 1_000).toFixed(1) + 'K'
  if (num % 1 !== 0)    return num.toFixed(2)
  return num.toLocaleString()
}
