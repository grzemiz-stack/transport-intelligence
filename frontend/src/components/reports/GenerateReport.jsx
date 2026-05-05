import { useState } from 'react'
import { generateReport } from '../../api/client'
import { FileText, Loader2 } from 'lucide-react'
import t from '../../utils/translations'

const REPORT_LANGUAGES = [
  { code: 'pl', label: 'Polski (PL)' },
  { code: 'en', label: 'English (EN)' },
  { code: 'de', label: 'Deutsch (DE)' },
  { code: 'fr', label: 'Français (FR)' },
  { code: 'it', label: 'Italiano (IT)' },
  { code: 'es', label: 'Español (ES)' },
]

export default function GenerateReport() {
  const [form, setForm] = useState({ report_type: 'biweekly', format: 'pdf', language: 'pl' })
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    setGenerating(true)
    setResult(null)
    generateReport(form)
      .then((res) => setResult({ success: true, data: res.data }))
      .catch(() => setResult({ success: false, data: { message: t.common.error } }))
      .finally(() => setGenerating(false))
  }

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-5">
      <h3 className="text-sm font-medium text-slate-400 flex items-center gap-2 mb-4">
        <FileText className="w-4 h-4" /> {t.reports.generateNewReport}
      </h3>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1">{t.reports.reportType}</label>
          <select
            value={form.report_type}
            onChange={(e) => setForm({ ...form, report_type: e.target.value })}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
          >
            <option value="biweekly">{t.reports.biweeklyRiskReport}</option>
            <option value="monthly">{t.reports.monthlyIntelligenceReport}</option>
            <option value="alert">{t.reports.alertReport}</option>
            <option value="custom">{t.reports.customReport}</option>
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">{t.reports.reportLanguage}</label>
          <select
            value={form.language}
            onChange={(e) => setForm({ ...form, language: e.target.value })}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
          >
            {REPORT_LANGUAGES.map((lang) => (
              <option key={lang.code} value={lang.code}>{lang.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">{t.reports.format}</label>
          <select
            value={form.format}
            onChange={(e) => setForm({ ...form, format: e.target.value })}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
          >
            <option value="pdf">PDF</option>
            <option value="html">HTML</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={generating}
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-500 disabled:opacity-50 transition-colors"
        >
          {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
          {generating ? t.reports.generating : t.reports.generateReport}
        </button>

        {result && (
          <div className={`p-3 rounded-lg text-sm ${result.success ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'}`}>
            {result.data?.message || t.reports.reportGenStarted}
          </div>
        )}
      </form>
    </div>
  )
}
