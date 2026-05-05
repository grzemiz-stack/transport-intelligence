import { Activity, AlertTriangle, Bot, Building2, TrendingUp, TrendingDown } from 'lucide-react'
import { formatNumber } from '../../utils/formatters'
import t from '../../utils/translations'

const cards = [
  { key: 'total_events', label: t.dashboard.totalEvents, icon: Activity, color: 'blue' },
  { key: 'active_alerts', label: t.dashboard.activeAlerts, icon: AlertTriangle, color: 'red' },
  { key: 'agents_running', label: t.dashboard.agentsRunning, icon: Bot, color: 'green' },
  { key: 'companies_at_risk', label: t.dashboard.companiesAtRisk, icon: Building2, color: 'orange' },
]

const colorMap = {
  blue: 'bg-blue-500/10 text-blue-400',
  red: 'bg-red-500/10 text-red-400',
  green: 'bg-green-500/10 text-green-400',
  orange: 'bg-orange-500/10 text-orange-400',
}

export default function StatsCards({ data }) {
  const merged = cards.map((c) => ({
    ...c,
    value: data?.[c.key] ?? 0,
    change: data?.[c.key + '_change'] ?? 0,
  }))

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      {merged.map(({ key, label, icon: Icon, color, value, change }) => (
        <div key={key} className="bg-[#1e293b] rounded-xl border border-slate-700 p-5 hover:border-slate-600 transition-colors">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-slate-400">{label}</span>
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${colorMap[color]}`}>
              <Icon className="w-5 h-5" />
            </div>
          </div>
          <div className="flex items-end gap-3">
            <span className="text-3xl font-bold text-white">{formatNumber(value)}</span>
            {change !== 0 && (
              <span className={`flex items-center gap-0.5 text-xs font-medium mb-1 ${change > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {change > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {change > 0 ? '+' : ''}{change}%
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
