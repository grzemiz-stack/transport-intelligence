import { useState, useEffect } from 'react'
import { fetchReports } from '../../api/client'
import client from '../../api/client'
import Badge from '../common/Badge'
import LoadingSpinner from '../common/LoadingSpinner'
import { formatDateTime } from '../../utils/formatters'
import { FileText, Download } from 'lucide-react'
import t from '../../utils/translations'

export default function ReportList() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchReports()
      .then((res) => setReports(Array.isArray(res.data) ? res.data : res.data.reports || []))
      .catch(() => setReports([]))
      .finally(() => setLoading(false))
  }, [])

  const handleDownload = async (id) => {
    try {
      const res = await client.get(`/reports/${id}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `report-${id}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Download failed:', err)
    }
  }

  if (loading) return <LoadingSpinner />

  if (reports.length === 0) {
    return (
      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-8 text-center">
        <FileText className="w-8 h-8 text-slate-600 mx-auto mb-2" />
        <p className="text-sm text-slate-500">{t.empty.noReports}</p>
      </div>
    )
  }

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 overflow-hidden">
      <div className="divide-y divide-slate-700/50">
        {reports.map((r) => (
          <div key={r.id} className="flex items-center gap-4 px-5 py-4 hover:bg-slate-800/50 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0">
              <FileText className="w-5 h-5 text-blue-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-white font-medium truncate">{t.reports[r.report_type] || r.report_type} — {r.id}</div>
              <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                <span>{formatDateTime(r.created_at)}</span>
                {r.pages && <span>{r.pages} {t.reports.pages}</span>}
                <Badge variant="status">{r.report_type}</Badge>
              </div>
            </div>
            <button onClick={() => handleDownload(r.id)} className="p-2 rounded-lg text-slate-400 hover:text-blue-400 hover:bg-slate-700/50 transition-colors" title={t.common.download}>
              <Download className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
