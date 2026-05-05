import { useState, useEffect } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { Search, Bell, User, LogOut } from 'lucide-react'
import t from '../../utils/translations'
import { getUser, logout } from '../../api/auth'
import { fetchActiveAlerts } from '../../api/client'

const routeNames = {
  '/': t.sidebar.dashboard,
  '/events': t.sidebar.events,
  '/map': t.sidebar.riskMap,
  '/agents': t.sidebar.agents,
  '/companies': t.sidebar.companies,
  '/alerts': t.sidebar.alerts,
  '/reports': t.sidebar.reports,
}

export default function Header() {
  const location = useLocation()
  const path = location.pathname
  const segments = path.split('/').filter(Boolean)
  const user = getUser()
  const [alertCount, setAlertCount] = useState(0)

  useEffect(() => {
    fetchActiveAlerts()
      .then((res) => {
        const data = res.data
        setAlertCount(Array.isArray(data) ? data.length : data?.alerts?.length || 0)
      })
      .catch(() => {})
  }, [])

  const breadcrumbs = [{ label: t.header.home, to: '/' }]
  if (segments.length > 0) {
    const base = '/' + segments[0]
    breadcrumbs.push({ label: routeNames[base] || segments[0], to: base })
  }
  if (segments.length > 1) {
    breadcrumbs.push({ label: segments[1], to: path })
  }

  return (
    <header className="h-16 bg-[#1e293b] border-b border-slate-700 flex items-center justify-between px-6 sticky top-0 z-30">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm">
        {breadcrumbs.map((b, i) => (
          <span key={b.to} className="flex items-center gap-2">
            {i > 0 && <span className="text-slate-600">/</span>}
            {i < breadcrumbs.length - 1 ? (
              <Link to={b.to} className="text-slate-400 hover:text-slate-200 transition-colors">
                {b.label}
              </Link>
            ) : (
              <span className="text-slate-200 font-medium">{b.label}</span>
            )}
          </span>
        ))}
      </nav>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder={t.header.searchPlaceholder}
            className="w-64 pl-9 pr-4 py-2 bg-slate-800 border border-slate-600 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
          />
        </div>

        {/* Notifications */}
        <button className="relative p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 transition-colors">
          <Bell className="w-5 h-5" />
          {alertCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-4.5 h-4.5 bg-red-500 text-[10px] text-white rounded-full flex items-center justify-center font-bold leading-none min-w-[18px] h-[18px]">
              {alertCount}
            </span>
          )}
        </button>

        {/* User info + logout */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white">
              <User className="w-4 h-4" />
            </div>
            <span className="text-sm text-slate-300 hidden lg:block">
              {user?.email || '—'}
            </span>
          </div>
          <button
            onClick={logout}
            title="Wyloguj"
            className="p-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-slate-700/50 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  )
}
