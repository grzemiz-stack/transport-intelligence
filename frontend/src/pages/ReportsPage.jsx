import ReportList from '../components/reports/ReportList'
import GenerateReport from '../components/reports/GenerateReport'
import t from '../utils/translations'

export default function ReportsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">{t.reports.title}</h1>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <ReportList />
        </div>
        <GenerateReport />
      </div>
    </div>
  )
}
