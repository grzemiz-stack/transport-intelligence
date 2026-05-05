import { SEVERITY_BG, STATUS_BG } from '../../utils/constants'

export default function Badge({ children, variant = 'severity', className = '' }) {
  const colorMap = variant === 'status' ? STATUS_BG : SEVERITY_BG
  const key = typeof children === 'string' ? children.toUpperCase() : ''
  const colors = colorMap[key] || colorMap[children] || 'bg-slate-500/20 text-slate-400 border-slate-500/30'

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${colors} ${className}`}>
      {children}
    </span>
  )
}
