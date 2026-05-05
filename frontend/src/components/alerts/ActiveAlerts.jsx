import { useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import Badge from '../common/Badge'
import { formatRelativeTime } from '../../utils/formatters'
import t from '../../utils/translations'

export default function ActiveAlerts({ alerts }) {
  const navigate = useNavigate()
  const data = alerts || []

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Bell className="w-4 h-4 text-red-400" />
        <h3 className="text-sm font-medium text-slate-400">{t.alerts.active}</h3>
        <span className="ml-auto bg-red-500/20 text-red-400 text-xs font-medium px-2 py-0.5 rounded-full">{data.length}</span>
      </div>
      {data.length === 0 ? (
        <div className="py-4 text-center">
          <p className="text-xs text-slate-500">{t.empty.noAlerts}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {data.map((a) => (
            <div
              key={a.id}
              onClick={() => navigate(`/alerts`)}
              className="p-3 bg-slate-800/50 rounded-lg hover:bg-slate-800 cursor-pointer transition-colors"
            >
              <div className="flex items-center gap-2 mb-1">
                <Badge>{a.severity}</Badge>
                <span className="text-[10px] text-slate-500">{formatRelativeTime(a.created_at)}</span>
              </div>
              <div className="text-xs text-slate-300">{a.title}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
