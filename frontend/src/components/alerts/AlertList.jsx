import { useState, useEffect } from 'react'
import { fetchAlerts, resolveAlert } from '../../api/client'
import Badge from '../common/Badge'
import LoadingSpinner from '../common/LoadingSpinner'
import { COUNTRIES, SEVERITY_LABELS } from '../../utils/constants'
import { formatDateTime } from '../../utils/formatters'
import t from '../../utils/translations'

const filterLabels = {
  all: t.alerts.all,
  active: t.alerts.active,
  resolved: t.alerts.resolved,
}

export default function AlertList() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    fetchAlerts()
      .then((res) => setAlerts(Array.isArray(res.data) ? res.data : res.data.alerts || []))
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false))
  }, [])

  const handleResolve = (id) => {
    resolveAlert(id, { resolution_note: '' })
      .then(() => setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, status: 'resolved', is_active: false } : a)))
      .catch(() => {})
  }

  const filtered = filter === 'all'
    ? alerts
    : alerts.filter((a) => (filter === 'active' ? (a.status === 'active' || a.is_active) : (a.status === 'resolved' || a.is_active === false)))

  if (loading) return <LoadingSpinner />

  return (
    <div className="space-y-4">
      {/* Filter tabs */}
      <div className="flex gap-2">
        {['all', 'active', 'resolved'].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filter === f ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            {filterLabels[f]}
            {f === 'active' && <span className="ml-1.5 bg-red-500/30 text-red-400 px-1.5 py-0.5 rounded-full text-[10px]">{alerts.filter((a) => a.status === 'active' || a.is_active).length}</span>}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-8 text-center">
          <p className="text-sm text-slate-500">{alerts.length === 0 ? t.empty.noAlerts : t.alerts.noAlertsDescription}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((alert) => (
            <div key={alert.id} className={`bg-[#1e293b] rounded-xl border p-5 ${(alert.status === 'active' || alert.is_active) ? 'border-slate-700' : 'border-slate-700/50 opacity-70'}`}>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge>{SEVERITY_LABELS[alert.severity] || alert.severity}</Badge>
                    <Badge variant="status">{alert.is_active ? t.alerts.active : alert.status === 'active' ? t.alerts.active : t.alerts.resolved}</Badge>
                    <span className="text-xs text-slate-500 font-mono">{alert.id}</span>
                  </div>
                  <h3 className="text-white font-medium mb-1">{alert.title}</h3>
                  <p className="text-sm text-slate-400 mb-3">{alert.description}</p>
                  <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                    <span>{t.alerts.created}: {formatDateTime(alert.created_at)}</span>
                    {alert.resolved_at && <span>{t.alerts.resolvedAt}: {formatDateTime(alert.resolved_at)}</span>}
                    <span>{t.alerts.events}: {alert.event_count || (alert.related_event_ids || []).length}</span>
                    <span>{t.alerts.countries}: {(alert.affected_countries || [alert.country_code].filter(Boolean)).map((cc) => `${COUNTRIES[cc]?.flag || ''} ${cc}`).join(', ')}</span>
                  </div>
                </div>
                {(alert.status === 'active' || alert.is_active) && (
                  <button
                    onClick={() => handleResolve(alert.id)}
                    className="ml-4 px-3 py-1.5 text-xs bg-green-500/10 text-green-400 border border-green-500/30 rounded-lg hover:bg-green-500/20 transition-colors shrink-0"
                  >
                    {t.alerts.resolve}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
