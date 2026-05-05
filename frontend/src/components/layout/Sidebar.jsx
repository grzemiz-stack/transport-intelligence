import { useState, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Calendar, Map, Bot, Building2, Bell, FileText, Shield,
} from 'lucide-react'
import { fetchAgentStatus } from '../../api/client'
import t from '../../utils/translations'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: t.sidebar.dashboard },
  { to: '/events', icon: Calendar, label: t.sidebar.events },
  { to: '/map', icon: Map, label: t.sidebar.riskMap },
  { to: '/agents', icon: Bot, label: t.sidebar.agents },
  { to: '/companies', icon: Building2, label: t.sidebar.companies },
  { to: '/alerts', icon: Bell, label: t.sidebar.alerts },
  { to: '/reports', icon: FileText, label: t.sidebar.reports },
]

export default function Sidebar() {
  const [agentCount, setAgentCount] = useState(null)

  useEffect(() => {
    fetchAgentStatus()
      .then((res) => {
        const data = res.data
        if (Array.isArray(data)) {
          setAgentCount(data.filter((c) => c.supervisor_status === 'running').length)
        } else if (data.countries) {
          setAgentCount(data.countries.filter((c) => c.supervisor_status === 'running').length)
        } else if (typeof data.running_count === 'number') {
          setAgentCount(data.running_count)
        }
      })
      .catch(() => setAgentCount(null))
  }, [])

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-64 bg-[#1e293b] border-r border-slate-700 flex flex-col z-40">
      {/* Logo */}
      <div className="h-16 flex items-center gap-3 px-6 border-b border-slate-700">
        <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <div className="font-bold text-sm text-white leading-tight">Transport</div>
          <div className="text-xs text-blue-400 leading-tight">Intelligence</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-600/20 text-blue-400'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
              }`
            }
          >
            <Icon className="w-5 h-5 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Status footer */}
      <div className="p-4 border-t border-slate-700">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className={`w-2 h-2 rounded-full ${agentCount !== null && agentCount > 0 ? 'bg-green-500 animate-pulse' : 'bg-slate-600'}`} />
          <span>{agentCount !== null ? `${agentCount} ${t.sidebar.agentsRunning}` : t.common.loading}</span>
        </div>
        <div className="mt-1 text-[10px] text-slate-600">v1.0.0 — EU Transport OSINT</div>
      </div>
    </aside>
  )
}
