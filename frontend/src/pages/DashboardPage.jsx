import { useState, useEffect } from 'react'
import { fetchDashboardOverview, fetchDashboardMap, fetchDashboardTrends, fetchCompaniesAtRisk } from '../api/client'
import StatsCards from '../components/dashboard/StatsCards'
import EventsChart from '../components/dashboard/EventsChart'
import SeverityPie from '../components/dashboard/SeverityPie'
import CountryBar from '../components/dashboard/CountryBar'
import LatestEvents from '../components/dashboard/LatestEvents'
import RiskMap from '../components/dashboard/RiskMap'
import t from '../utils/translations'

export default function DashboardPage() {
  const [overview, setOverview] = useState(null)
  const [mapData, setMapData] = useState(null)
  const [trends, setTrends] = useState(null)
  const [atRiskCount, setAtRiskCount] = useState(0)

  useEffect(() => {
    fetchDashboardOverview().then((r) => setOverview(r.data)).catch(() => {})
    fetchDashboardMap().then((r) => setMapData(r.data)).catch(() => {})
    fetchDashboardTrends().then((r) => setTrends(r.data)).catch(() => {})
    fetchCompaniesAtRisk()
      .then((r) => {
        const data = r.data
        setAtRiskCount(Array.isArray(data) ? data.length : data?.companies?.length || 0)
      })
      .catch(() => {})
  }, [])

  const statsData = overview ? {
    total_events: overview.events_this_month,
    active_alerts: overview.active_alerts_count,
    agents_running: overview.agents_summary?.running ?? 0,
    companies_at_risk: atRiskCount,
  } : null

  const severityData = overview?.events_by_severity
    ? Object.entries(overview.events_by_severity).map(([name, value]) => ({ name, value }))
    : null

  const countryData = overview?.top_countries?.map(c => ({
    country: c.country_code, events: c.count
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">{t.dashboard.title}</h1>
        <span className="text-xs text-slate-500">{t.header.lastUpdated}: {new Date().toLocaleTimeString('pl-PL')}</span>
      </div>

      <StatsCards data={statsData} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <EventsChart data={trends?.daily_counts} />
        </div>
        <SeverityPie data={severityData} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <RiskMap hotspots={mapData?.hotspots} />
        <CountryBar data={countryData} />
      </div>

      <LatestEvents events={overview?.latest_events} />
    </div>
  )
}
