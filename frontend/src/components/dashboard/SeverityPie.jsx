import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { SEVERITY_COLORS, SEVERITY_LABELS } from '../../utils/constants'
import t from '../../utils/translations'

const renderLabel = ({ name, percent }) => `${SEVERITY_LABELS[name] || name} ${(percent * 100).toFixed(0)}%`

export default function SeverityPie({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
        <h3 className="text-sm font-medium text-slate-400 mb-4">{t.dashboard.severityBreakdown}</h3>
        <div className="h-64 flex items-center justify-center">
          <p className="text-sm text-slate-500">{t.empty.noChartData}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
      <h3 className="text-sm font-medium text-slate-400 mb-4">{t.dashboard.severityBreakdown}</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={85}
              paddingAngle={3}
              dataKey="value"
              label={renderLabel}
              labelLine={{ stroke: '#64748b' }}
            >
              {data.map((entry) => (
                <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name] || '#64748b'} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
              labelStyle={{ color: '#e2e8f0' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
