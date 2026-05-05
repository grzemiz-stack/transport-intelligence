import { COUNTRIES } from '../../utils/constants'
import AgentControls from './AgentControls'
import t from '../../utils/translations'

const agentStatusIcon = {
  running: '\u2705',
  active: '\u2705',
  stopped: '\u274C',
  error: '\u274C',
  warning: '\u26A0\uFE0F',
  idle: '\u23F8\uFE0F',
}

export default function CountryCard({ country, onStart, onStop, onRestart }) {
  const cc = country.country_code
  const info = COUNTRIES[cc] || { name: cc, flag: '' }
  const agents = country.agents || []
  const hasErrors = agents.some((a) => a.status === 'error')
  const eventsToday = country.events_today ?? 0

  return (
    <div className={`bg-[#1e293b] rounded-xl border transition-colors p-4 ${hasErrors ? 'border-red-500/50' : 'border-slate-700 hover:border-slate-600'}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">{info.flag}</span>
          <div>
            <div className="text-sm font-medium text-white">{info.name}</div>
            <div className="text-xs text-slate-500">{cc}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${country.supervisor_status === 'running' ? 'bg-green-500' : 'bg-red-500'}`} />
          <AgentControls countryCode={cc} status={country.supervisor_status} onStart={onStart} onStop={onStop} onRestart={onRestart} />
        </div>
      </div>

      {/* Agent list */}
      <div className="space-y-1 mb-3">
        {agents.map((agent) => (
          <div key={agent.type || agent.agent_type} className="flex items-center justify-between text-xs">
            <span className="text-slate-400">{agent.type || agent.agent_type}</span>
            <span>{agentStatusIcon[agent.status] || '\u2753'}</span>
          </div>
        ))}
      </div>

      {/* Footer stats */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-700">
        <div className="text-xs">
          <span className="text-slate-500">{t.agents.eventsToday}: </span>
          <span className="text-white font-medium">{eventsToday}</span>
        </div>
        {hasErrors && (
          <span className="text-xs text-red-400 font-medium">{t.agents.errorsDetected}</span>
        )}
      </div>
    </div>
  )
}
