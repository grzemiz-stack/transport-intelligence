import CompanyList from '../components/companies/CompanyList'
import AtRiskPanel from '../components/companies/AtRiskPanel'
import t from '../utils/translations'

export default function CompaniesPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">{t.companies.title}</h1>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <CompanyList />
        </div>
        <AtRiskPanel />
      </div>
    </div>
  )
}
