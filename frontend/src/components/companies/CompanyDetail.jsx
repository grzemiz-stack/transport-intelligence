import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Building2, TrendingUp, AlertTriangle, Shield } from 'lucide-react'
import { fetchCompany, fetchCompanyTimeline } from '../../api/client'
import Badge from '../common/Badge'
import LoadingSpinner from '../common/LoadingSpinner'
import { COUNTRIES, EVENT_TYPE_LABELS } from '../../utils/constants'
import { formatDate } from '../../utils/formatters'
import t from '../../utils/translations'

export default function CompanyDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [company, setCompany] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    Promise.all([
      fetchCompany(id).then((r) => r.data).catch(() => null),
      fetchCompanyTimeline(id).then((r) => r.data.events || r.data || []).catch(() => []),
    ])
      .then(([c, tl]) => {
        if (!c) setError(true)
        setCompany(c)
        setTimeline(Array.isArray(tl) ? tl : [])
      })
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <LoadingSpinner />
  if (error || !company) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
          <ArrowLeft className="w-4 h-4" /> {t.companies.title}
        </button>
        <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-8 text-center">
          <p className="text-sm text-slate-500">{t.common.error}</p>
        </div>
      </div>
    )
  }

  const c = company

  return (
    <div className="space-y-6">
      <button onClick={() => navigate(-1)} className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
        <ArrowLeft className="w-4 h-4" /> {t.companies.title}
      </button>

      {/* Header card */}
      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-xl bg-blue-500/10 flex items-center justify-center">
              <Building2 className="w-7 h-7 text-blue-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-white">{c.name}</h1>
              <div className="flex items-center gap-3 mt-1 text-sm text-slate-400">
                <span>{COUNTRIES[c.country_code]?.flag} {COUNTRIES[c.country_code]?.name}</span>
                <span>{c.company_type}</span>
                {c.fleet_size && <span>{c.fleet_size} {t.companies.vehicles}</span>}
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className={`text-3xl font-bold ${(c.risk_score || 0) >= 70 ? 'text-red-400' : (c.risk_score || 0) >= 40 ? 'text-orange-400' : 'text-green-400'}`}>
              {c.risk_score || 0}
            </div>
            <div className="text-xs text-slate-500">{t.companies.riskScore}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500">{t.companies.financial}</div>
            <div className="mt-1"><Badge variant="status">{c.financial_status || '—'}</Badge></div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500">{t.companies.events}</div>
            <div className="text-lg font-semibold text-white mt-1">{c.related_events?.length || 0}</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500">{t.companies.license}</div>
            <div className="text-sm text-white mt-1">{c.registry_id || '—'}</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500">{t.companies.vat}</div>
            <div className="text-sm text-white mt-1">{c.tax_id || '—'}</div>
          </div>
        </div>
      </div>

      {c.risk_breakdown && Object.keys(c.risk_breakdown).length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
            <h3 className="text-sm font-medium text-slate-400 flex items-center gap-2 mb-3">
              <AlertTriangle className="w-4 h-4 text-orange-400" /> {t.companies.riskFactors}
            </h3>
            <ul className="space-y-2">
              {Object.entries(c.risk_breakdown).map(([key, val], i) => (
                <li key={i} className="text-sm text-slate-300 flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-orange-400 mt-1.5 shrink-0" />
                  {key}: {val}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Timeline */}
      {timeline.length > 0 && (
        <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
          <h3 className="text-sm font-medium text-slate-400 mb-4">{t.companies.eventHistory}</h3>
          <div className="space-y-3">
            {timeline.map((ev, i) => (
              <div key={i} className="flex items-start gap-3 p-3 bg-slate-800/30 rounded-lg">
                <div className="text-xs text-slate-500 min-w-[80px] pt-0.5">{formatDate(ev.date)}</div>
                <Badge>{ev.severity}</Badge>
                <div className="text-sm text-slate-300">{ev.title}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
