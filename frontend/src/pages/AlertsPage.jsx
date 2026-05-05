import AlertList from '../components/alerts/AlertList'
import t from '../utils/translations'

export default function AlertsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">{t.alerts.title}</h1>
      <AlertList />
    </div>
  )
}
