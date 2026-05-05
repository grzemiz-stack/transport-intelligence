import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchEvents } from '../../api/client'
import Badge from '../common/Badge'
import LoadingSpinner from '../common/LoadingSpinner'
import EmptyState from '../common/EmptyState'
import EventFilters from './EventFilters'
import { COUNTRIES, EVENT_TYPE_LABELS, SEVERITY_LABELS } from '../../utils/constants'
import { formatDateTime, truncate } from '../../utils/formatters'
import t from '../../utils/translations'

const TIER_BORDER_COLORS = {
  1: 'border-l-red-500',
  2: 'border-l-orange-500',
  3: 'border-l-yellow-500',
  4: 'border-l-slate-600',
}

const TIER_BADGE_COLORS = {
  1: 'bg-red-500/20 text-red-400',
  2: 'bg-orange-500/20 text-orange-400',
  3: 'bg-yellow-500/20 text-yellow-400',
  4: 'bg-slate-600/20 text-slate-400',
}

export default function EventList() {
  const navigate = useNavigate()
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({ country_code: '', event_type: '', severity: '', date_from: '', date_to: '', tier: '' })
  const [page, setPage] = useState(0)
  const pageSize = 10

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    params.limit = pageSize
    params.offset = page * pageSize
    // If no tier filter, pass include_low=true to show all (tier filter dropdown handles selection)
    if (!params.tier) params.include_low = true
    fetchEvents(params)
      .then((res) => { if (!cancelled) setEvents(res.data.events || res.data || []) })
      .catch(() => { if (!cancelled) setEvents([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [filters, page])

  return (
    <div className="space-y-4">
      <EventFilters filters={filters} onChange={(f) => { setFilters(f); setPage(0) }} />

      <div className="bg-[#1e293b] rounded-xl border border-slate-700">
        {loading ? (
          <LoadingSpinner />
        ) : events.length === 0 ? (
          <EmptyState title={t.events.noEventsFound} description={t.events.tryAdjustingFilters} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.tier.label}</th>
                    <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.events.date}</th>
                    <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.events.country}</th>
                    <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.events.type}</th>
                    <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.events.severity}</th>
                    <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.events.titleCol}</th>
                    <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.events.trust}</th>
                    <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.events.source}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {events.map((ev) => {
                    const tier = ev.intelligence_tier || 4
                    return (
                      <tr
                        key={ev.id}
                        onClick={() => navigate(`/events/${ev.id}`)}
                        className={`hover:bg-slate-800/50 cursor-pointer transition-colors border-l-4 ${TIER_BORDER_COLORS[tier] || 'border-l-slate-600'}`}
                      >
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${TIER_BADGE_COLORS[tier] || TIER_BADGE_COLORS[4]}`}>
                            {t.tier[`short_${tier}`] || `T${tier}`}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-400">{formatDateTime(ev.date)}</td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          {COUNTRIES[ev.country_code]?.flag} {ev.country_code}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-400">{EVENT_TYPE_LABELS[ev.event_type] || ev.event_type}</td>
                        <td className="px-4 py-3 whitespace-nowrap"><Badge>{SEVERITY_LABELS[ev.severity] || ev.severity}</Badge></td>
                        <td className="px-4 py-3 text-slate-300 max-w-sm">{truncate(ev.title, 55)}</td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full bg-blue-500"
                                style={{ width: `${(ev.trust_score || 0) * 100}%` }}
                              />
                            </div>
                            <span className="text-xs text-slate-500">{Math.round((ev.trust_score || 0) * 100)}%</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-500">{ev.source_name}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {/* Pagination */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700">
              <span className="text-xs text-slate-500">{t.events.showing} {page * pageSize + 1}–{page * pageSize + events.length} {t.events.events}</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(Math.max(0, page - 1))}
                  disabled={page === 0}
                  className="px-3 py-1.5 text-xs bg-slate-800 border border-slate-600 rounded-lg text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {t.events.previous}
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={events.length < pageSize}
                  className="px-3 py-1.5 text-xs bg-slate-800 border border-slate-600 rounded-lg text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {t.events.next}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
