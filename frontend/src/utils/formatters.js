export function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatDateTime(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function formatRelativeTime(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  const now = new Date()
  const diffMs = now - d
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH}h ago`
  const diffD = Math.floor(diffH / 24)
  if (diffD < 7) return `${diffD}d ago`
  return formatDate(dateStr)
}

export function formatNumber(num) {
  if (num == null) return '—'
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M'
  if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K'
  return num.toLocaleString()
}

export function formatPercent(num) {
  if (num == null) return '—'
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(1)}%`
}

export function formatRiskScore(score) {
  if (score == null) return '—'
  return `${Math.round(score)}/100`
}

export function truncate(str, len = 60) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}
