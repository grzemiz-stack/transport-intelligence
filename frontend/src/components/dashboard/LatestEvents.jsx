import { useNavigate } from 'react-router-dom'
import Badge from '../common/Badge'
import { COUNTRIES, EVENT_TYPE_LABELS, SEVERITY_LABELS } from '../../utils/constants'
import { formatRelativeTime, truncate } from '../../utils/formatters'
import t from '../../utils/translations'

export default function LatestEvents({ events }) {
  const navigate = useNavigate()
  const data = events || []

  if (data.length === 0) {
    return (
      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
        <h3 className="text-sm font-medium text-slate-400 mb-4">{t.dashboard.latestEvents}</h3>
        <div className="py-8 text-center">
          <p className="text-sm text-slate-500">{t.empty.noEvents}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-slate-400">{t.dashboard.latestEvents}</h3>
        <button onClick={() => navigate('/events')} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
          {t.dashboard.viewAll}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="px-3 py-2 text-left text-xs text-slate-500 font-medium">{t.events.time}</th>
              <th className="px-3 py-2 text-left text-xs text-slate-500 font-medium">{t.events.country}</th>
              <th className="px-3 py-2 text-left text-xs text-slate-500 font-medium">{t.events.type}</th>
              <th className="px-3 py-2 text-left text-xs text-slate-500 font-medium">{t.events.severity}</th>
              <th className="px-3 py-2 text-left text-xs text-slate-500 font-medium">{t.events.titleCol}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {data.slice(0, 8).map((ev) => (
              <tr
                key={ev.id}
                onClick={() => navigate(`/events/${ev.id}`)}
                className="hover:bg-slate-800/50 cursor-pointer transition-colors"
              >
                <td className="px-3 py-2.5 whitespace-nowrap text-xs text-slate-500">{formatRelativeTime(ev.date)}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <span className="text-sm">{COUNTRIES[ev.country_code]?.flag || ''} {ev.country_code}</span>
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap text-xs text-slate-400">{EVENT_TYPE_LABELS[ev.event_type] || ev.event_type}</td>
                <td className="px-3 py-2.5 whitespace-nowrap"><Badge>{SEVERITY_LABELS[ev.severity] || ev.severity}</Badge></td>
                <td className="px-3 py-2.5 text-slate-300 text-xs max-w-xs">{truncate(ev.title, 55)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
