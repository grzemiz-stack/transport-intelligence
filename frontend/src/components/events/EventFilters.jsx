import { EVENT_TYPES, EVENT_TYPE_LABELS, COUNTRIES, SEVERITY_LABELS } from '../../utils/constants'
import t from '../../utils/translations'

const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']
const tiers = [1, 2, 3, 4]
const countryEntries = Object.entries(COUNTRIES).sort((a, b) => a[1].name.localeCompare(b[1].name))

export default function EventFilters({ filters, onChange }) {
  const update = (key, value) => onChange({ ...filters, [key]: value })

  return (
    <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-4 flex flex-wrap gap-3 items-end">
      <div className="flex-1 min-w-[160px]">
        <label className="block text-xs text-slate-500 mb-1">{t.tier.label}</label>
        <select
          value={filters.tier || ''}
          onChange={(e) => update('tier', e.target.value)}
          className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
        >
          <option value="">{t.tier.all}</option>
          {tiers.map((tier) => (
            <option key={tier} value={tier}>{t.tier[tier]}</option>
          ))}
        </select>
      </div>

      <div className="flex-1 min-w-[160px]">
        <label className="block text-xs text-slate-500 mb-1">{t.events.country}</label>
        <select
          value={filters.country_code || ''}
          onChange={(e) => update('country_code', e.target.value)}
          className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
        >
          <option value="">{t.events.allCountries}</option>
          {countryEntries.map(([code, { name, flag }]) => (
            <option key={code} value={code}>{flag} {name}</option>
          ))}
        </select>
      </div>

      <div className="flex-1 min-w-[160px]">
        <label className="block text-xs text-slate-500 mb-1">{t.events.eventType}</label>
        <select
          value={filters.event_type || ''}
          onChange={(e) => update('event_type', e.target.value)}
          className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
        >
          <option value="">{t.events.allTypes}</option>
          {EVENT_TYPES.map((tp) => (
            <option key={tp} value={tp}>{EVENT_TYPE_LABELS[tp]}</option>
          ))}
        </select>
      </div>

      <div className="flex-1 min-w-[140px]">
        <label className="block text-xs text-slate-500 mb-1">{t.events.severity}</label>
        <select
          value={filters.severity || ''}
          onChange={(e) => update('severity', e.target.value)}
          className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
        >
          <option value="">{t.events.allSeverities}</option>
          {severities.map((s) => (
            <option key={s} value={s}>{SEVERITY_LABELS[s]}</option>
          ))}
        </select>
      </div>

      <div className="flex-1 min-w-[140px]">
        <label className="block text-xs text-slate-500 mb-1">{t.events.dateFrom}</label>
        <input
          type="date"
          value={filters.date_from || ''}
          onChange={(e) => update('date_from', e.target.value)}
          className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
        />
      </div>

      <div className="flex-1 min-w-[140px]">
        <label className="block text-xs text-slate-500 mb-1">{t.events.dateTo}</label>
        <input
          type="date"
          value={filters.date_to || ''}
          onChange={(e) => update('date_to', e.target.value)}
          className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
        />
      </div>

      <button
        onClick={() => onChange({ country_code: '', event_type: '', severity: '', date_from: '', date_to: '', tier: '' })}
        className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-700 rounded-lg transition-colors"
      >
        {t.events.reset}
      </button>
    </div>
  )
}
