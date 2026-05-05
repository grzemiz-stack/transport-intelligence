import AgentsDashboard from '../components/agents/AgentsDashboard'
import t from '../utils/translations'

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">{t.agents.title}</h1>
      <AgentsDashboard />
    </div>
  )
}
