import { Inbox } from 'lucide-react'

export default function EmptyState({ icon: Icon = Inbox, title = 'No data', description = 'No results found.' }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <Icon className="w-12 h-12 text-slate-600" />
      <h3 className="text-lg font-medium text-slate-300">{title}</h3>
      <p className="text-sm text-slate-500">{description}</p>
    </div>
  )
}
