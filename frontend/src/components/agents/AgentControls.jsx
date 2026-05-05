import { Play, Square, RotateCcw } from 'lucide-react'

export default function AgentControls({ countryCode, onStart, onStop, onRestart, status }) {
  const isRunning = status === 'running' || status === 'active'

  return (
    <div className="flex gap-1.5">
      {!isRunning && (
        <button
          onClick={() => onStart?.(countryCode)}
          className="p-1.5 rounded-md bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
          title="Start"
        >
          <Play className="w-3.5 h-3.5" />
        </button>
      )}
      {isRunning && (
        <button
          onClick={() => onStop?.(countryCode)}
          className="p-1.5 rounded-md bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
          title="Stop"
        >
          <Square className="w-3.5 h-3.5" />
        </button>
      )}
      <button
        onClick={() => onRestart?.(countryCode)}
        className="p-1.5 rounded-md bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
        title="Restart"
      >
        <RotateCcw className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
