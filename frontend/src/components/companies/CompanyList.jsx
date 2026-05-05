import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchCompanies } from '../../api/client'
import Badge from '../common/Badge'
import LoadingSpinner from '../common/LoadingSpinner'
import { COUNTRIES, FINANCIAL_STATUS_LABELS } from '../../utils/constants'
import t from '../../utils/translations'

function riskBar(score) {
  const color = score >= 70 ? 'bg-red-500' : score >= 40 ? 'bg-orange-500' : score >= 20 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className={`text-xs font-medium ${score >= 70 ? 'text-red-400' : score >= 40 ? 'text-orange-400' : 'text-slate-400'}`}>{score}</span>
    </div>
  )
}

export default function CompanyList() {
  const navigate = useNavigate()
  const [companies, setCompanies] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchCompanies()
      .then((res) => {
        const data = Array.isArray(res.data) ? res.data : res.data.companies || []
        setCompanies(data)
      })
      .catch(() => setCompanies([]))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSpinner />

  if (companies.length === 0) {
    return (
      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-8 text-center">
        <p className="text-sm text-slate-500">{t.empty.noCompanies}</p>
      </div>
    )
  }

  const sorted = [...companies].sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.companies.company}</th>
              <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.companies.country}</th>
              <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.companies.type}</th>
              <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.companies.financial}</th>
              <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.companies.riskScore}</th>
              <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.companies.events}</th>
              <th className="px-4 py-3 text-left text-xs text-slate-500 font-medium">{t.companies.fleet}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {sorted.map((c) => (
              <tr
                key={c.id}
                onClick={() => navigate(`/companies/${c.id}`)}
                className={`hover:bg-slate-800/50 cursor-pointer transition-colors ${
                  c.financial_status === 'BANKRUPT' ? 'bg-red-500/5' : c.financial_status === 'CRITICAL' ? 'bg-red-500/5' : ''
                }`}
              >
                <td className="px-4 py-3 text-white font-medium">{c.name}</td>
                <td className="px-4 py-3">{COUNTRIES[c.country_code]?.flag} {c.country_code}</td>
                <td className="px-4 py-3 text-xs text-slate-400">{c.company_type}</td>
                <td className="px-4 py-3"><Badge variant="status">{FINANCIAL_STATUS_LABELS[c.financial_status] || c.financial_status}</Badge></td>
                <td className="px-4 py-3">{riskBar(c.risk_score || 0)}</td>
                <td className="px-4 py-3 text-slate-300">{c.events_count || 0}</td>
                <td className="px-4 py-3 text-slate-400">{c.fleet_size?.toLocaleString() || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
