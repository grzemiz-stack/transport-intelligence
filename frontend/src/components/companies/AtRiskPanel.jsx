import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { fetchCompaniesAtRisk } from '../../api/client'
import { COUNTRIES, FINANCIAL_STATUS_LABELS } from '../../utils/constants'
import t from '../../utils/translations'

const statusColors = {
  WARNING: 'text-yellow-400',
  CRITICAL: 'text-red-400',
  BANKRUPT: 'text-red-500',
}

export default function AtRiskPanel() {
  const navigate = useNavigate()
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchCompaniesAtRisk()
      .then((res) => setData(Array.isArray(res.data) ? res.data : res.data.companies || []))
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
      <div className="flex items-center gap-2 mb-4">
        <AlertTriangle className="w-4 h-4 text-orange-400" />
        <h3 className="text-sm font-medium text-slate-400">{t.companies.companiesAtRisk}</h3>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-6">
          <div className="animate-spin w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full" />
        </div>
      ) : data.length === 0 ? (
        <div className="py-6 text-center">
          <p className="text-sm text-slate-500">{t.empty.collecting}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.map((c) => (
            <div
              key={c.id}
              onClick={() => navigate(`/companies/${c.id}`)}
              className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg hover:bg-slate-800 cursor-pointer transition-colors"
            >
              <div>
                <div className="text-sm text-white font-medium">{c.name}</div>
                <div className="text-xs text-slate-500">
                  {COUNTRIES[c.country_code]?.flag} {COUNTRIES[c.country_code]?.name} — {c.events_count || 0} {t.companies.events.toLowerCase()}
                </div>
              </div>
              <div className="text-right">
                <div className={`text-lg font-bold ${(c.risk_score || 0) >= 80 ? 'text-red-400' : (c.risk_score || 0) >= 50 ? 'text-orange-400' : 'text-yellow-400'}`}>
                  {c.risk_score || 0}
                </div>
                <div className={`text-[10px] font-medium ${statusColors[c.financial_status] || 'text-slate-400'}`}>
                  {FINANCIAL_STATUS_LABELS[c.financial_status] || c.financial_status}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
