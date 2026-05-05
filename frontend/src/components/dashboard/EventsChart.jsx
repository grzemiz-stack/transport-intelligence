import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import t from '../../utils/translations'

export default function EventsChart({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
        <h3 className="text-sm font-medium text-slate-400 mb-4">{t.dashboard.eventsLast30Days}</h3>
        <div className="h-64 flex items-center justify-center">
          <p className="text-sm text-slate-500">{t.empty.noChartData}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
      <h3 className="text-sm font-medium text-slate-400 mb-4">{t.dashboard.eventsLast30Days}</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorEvents" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
              labelStyle={{ color: '#e2e8f0' }}
              itemStyle={{ color: '#3b82f6' }}
            />
            <Area type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} fill="url(#colorEvents)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
