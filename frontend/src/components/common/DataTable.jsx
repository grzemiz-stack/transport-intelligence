import { useState } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import EmptyState from './EmptyState'

export default function DataTable({ columns, data, onRowClick, emptyText = 'No data available' }) {
  const [sortKey, setSortKey] = useState(null)
  const [sortDir, setSortDir] = useState('asc')

  const handleSort = (key) => {
    if (!key) return
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const sorted = sortKey
    ? [...data].sort((a, b) => {
        const av = a[sortKey], bv = b[sortKey]
        if (av == null) return 1
        if (bv == null) return -1
        const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv
        return sortDir === 'asc' ? cmp : -cmp
      })
    : data

  if (!data || data.length === 0) {
    return <EmptyState title={emptyText} />
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-700">
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => col.sortable !== false && handleSort(col.key)}
                className={`px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider ${
                  col.sortable !== false ? 'cursor-pointer hover:text-slate-200 select-none' : ''
                }`}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {col.sortable !== false && (
                    sortKey === col.key
                      ? (sortDir === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)
                      : <ChevronsUpDown className="w-3 h-3 opacity-30" />
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/50">
          {sorted.map((row, i) => (
            <tr
              key={row.id ?? i}
              onClick={() => onRowClick?.(row)}
              className={`hover:bg-slate-800/50 transition-colors ${onRowClick ? 'cursor-pointer' : ''}`}
            >
              {columns.map((col) => (
                <td key={col.key} className="px-4 py-3 whitespace-nowrap text-slate-300">
                  {col.render ? col.render(row[col.key], row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
