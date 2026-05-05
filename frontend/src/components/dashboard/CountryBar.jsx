import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import t from '../../utils/translations'

export default function CountryBar({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
        <h3 className="text-sm font-medium text-slate-400 mb-4">{t.dashboard.top10Countries}</h3>
        <div className="h-64 flex items-center justify-center">
          <p className="text-sm text-slate-500">{t.empty.noChartData}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
      <h3 className="text-sm font-medium text-slate-400 mb-4">{t.dashboard.top10Countries}</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, left: 5, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="country" tick={{ fontSize: 12, fill: '#94a3b8', fontWeight: 500 }} axisLine={false} tickLine={false} width={30} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
              labelStyle={{ color: '#e2e8f0' }}
              itemStyle={{ color: '#3b82f6' }}
            />
            <Bar dataKey="events" fill="#3b82f6" radius={[0, 4, 4, 0]} barSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
