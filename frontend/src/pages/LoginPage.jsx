import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield } from 'lucide-react'
import { login } from '../api/auth'

export default function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.response?.data?.detail || 'Nie udalo sie zalogowac')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0f172a] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600/20 mb-4">
            <Shield className="w-8 h-8 text-blue-400" />
          </div>
          <h1 className="text-2xl font-bold text-white">Transport Intelligence</h1>
          <p className="text-slate-400 mt-1">European Transport Risk Intelligence Platform</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-[#1e293b] rounded-xl p-8 border border-slate-700 shadow-2xl">
          <h2 className="text-lg font-semibold text-white mb-6">Zaloguj sie</h2>

          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm text-slate-400 mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@transport-intel.com"
              required
              className="w-full px-4 py-2.5 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm text-slate-400 mb-1.5">Haslo</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full px-4 py-2.5 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 text-white font-medium rounded-lg transition-colors"
          >
            {loading ? 'Logowanie...' : 'Zaloguj sie'}
          </button>
        </form>

        <p className="text-center text-slate-600 text-xs mt-6">
          Transport Intelligence v1.0 — Secure Access
        </p>
      </div>
    </div>
  )
}
