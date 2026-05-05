import { useState, useEffect } from 'react'
import { fetchAgentStatus, startCountryAgents, stopCountryAgents, restartCountryAgents } from '../../api/client'
import CountryCard from './CountryCard'
import LoadingSpinner from '../common/LoadingSpinner'
import t from '../../utils/translations'

export default function AgentsDashboard() {
  const [countries, setCountries] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchAgentStatus()
      .then((res) => {
        const data = res.data
        if (Array.isArray(data)) setCountries(data)
        else if (data.countries) setCountries(data.countries)
        else setCountries([])
      })
      .catch(() => setCountries([]))
      .finally(() => setLoading(false))
  }, [])

  const handleStart = (cc) => startCountryAgents(cc).catch(() => {})
  const handleStop = (cc) => stopCountryAgents(cc).catch(() => {})
  const handleRestart = (cc) => restartCountryAgents(cc).catch(() => {})

  if (loading) return <LoadingSpinner />

  if (countries.length === 0) {
    return (
      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-8 text-center">
        <p className="text-sm text-slate-500">{t.empty.noAgents}</p>
      </div>
    )
  }

  const running = countries.filter((c) => c.supervisor_status === 'running').length
  const errors = countries.reduce((sum, c) => sum + (c.agents?.filter((a) => a.status === 'error').length || 0), 0)

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center gap-6 bg-[#1e293b] rounded-xl border border-slate-700 px-5 py-3">
        <div className="text-sm">
          <span className="text-slate-400">{t.agents.countries}: </span>
          <span className="text-white font-medium">{countries.length}</span>
        </div>
        <div className="text-sm">
          <span className="text-slate-400">{t.agents.running}: </span>
          <span className="text-green-400 font-medium">{running}</span>
        </div>
        <div className="text-sm">
          <span className="text-slate-400">{t.agents.errors}: </span>
          <span className={`font-medium ${errors > 0 ? 'text-red-400' : 'text-green-400'}`}>{errors}</span>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
        {countries.map((country) => (
          <CountryCard
            key={country.country_code}
            country={country}
            onStart={handleStart}
            onStop={handleStop}
            onRestart={handleRestart}
          />
        ))}
      </div>
    </div>
  )
}
