import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, MapPin, Calendar, Shield, ExternalLink, Globe } from 'lucide-react'
import { fetchEvent, translateEvent } from '../../api/client'
import Badge from '../common/Badge'
import LoadingSpinner from '../common/LoadingSpinner'
import { COUNTRIES, EVENT_TYPE_LABELS } from '../../utils/constants'
import { formatDateTime } from '../../utils/formatters'
import t from '../../utils/translations'

export default function EventDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [event, setEvent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [translating, setTranslating] = useState(false)
  const [translation, setTranslation] = useState(null)

  useEffect(() => {
    fetchEvent(id)
      .then((res) => {
        setEvent(res.data)
        if (res.data.is_translated && res.data.translated_title) {
          setTranslation({
            translated_title: res.data.translated_title,
            translated_description: res.data.translated_description,
          })
        }
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [id])

  const handleTranslate = async () => {
    setTranslating(true)
    try {
      const res = await translateEvent(id)
      setTranslation(res.data)
      setEvent((prev) => ({ ...prev, is_translated: true, ...res.data }))
    } catch (err) {
      console.error('Translation failed:', err)
    } finally {
      setTranslating(false)
    }
  }

  if (loading) return <LoadingSpinner />
  if (error || !event) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
          <ArrowLeft className="w-4 h-4" /> {t.events.title}
        </button>
        <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-8 text-center">
          <p className="text-sm text-slate-500">{t.common.error}</p>
        </div>
      </div>
    )
  }

  const ev = event
  const showTranslateBtn = ev.language && ev.language !== 'pl' && !translation

  return (
    <div className="space-y-6">
      <button onClick={() => navigate(-1)} className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors">
        <ArrowLeft className="w-4 h-4" /> {t.events.title}
      </button>

      <div className="bg-[#1e293b] rounded-xl border border-slate-700 p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Badge>{ev.severity}</Badge>
              <span className="text-xs text-slate-500 font-mono">{ev.id}</span>
              {ev.is_verified && (
                <span className="flex items-center gap-1 text-xs text-green-400">
                  <Shield className="w-3 h-3" /> {t.events.verified}
                </span>
              )}
            </div>
            <h1 className="text-xl font-semibold text-white">{ev.title}</h1>
            {translation?.translated_title && (
              <p className="text-base text-blue-300 mt-1">{translation.translated_title}</p>
            )}
          </div>
          {showTranslateBtn && (
            <button
              onClick={handleTranslate}
              disabled={translating}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600/20 border border-blue-500/30 rounded-lg text-xs text-blue-400 hover:bg-blue-600/30 transition-colors disabled:opacity-50"
              title={t.events.translateToPolish}
            >
              <Globe className="w-3.5 h-3.5" />
              {translating ? t.events.translating : t.events.translate}
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">{t.events.country}</div>
            <div className="text-sm text-white">{COUNTRIES[ev.country_code]?.flag} {COUNTRIES[ev.country_code]?.name || ev.country_code}</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">{t.events.type}</div>
            <div className="text-sm text-white">{EVENT_TYPE_LABELS[ev.event_type] || ev.event_type}</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1 flex items-center gap-1"><Calendar className="w-3 h-3" /> {t.events.date}</div>
            <div className="text-sm text-white">{formatDateTime(ev.date)}</div>
          </div>
          <div className="bg-slate-800/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">{t.events.trust}</div>
            <div className="flex items-center gap-2">
              <div className="w-20 h-2 bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${(ev.trust_score || 0) * 100}%` }} />
              </div>
              <span className="text-sm text-white">{Math.round((ev.trust_score || 0) * 100)}%</span>
            </div>
          </div>
        </div>

        {ev.description && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-slate-400 mb-2">{t.events.description}</h3>
            <p className="text-sm text-slate-300 leading-relaxed">{ev.description}</p>
            {translation?.translated_description && (
              <div className="mt-3 pl-3 border-l-2 border-blue-500/40">
                <p className="text-xs text-blue-400 mb-1">{t.events.translationPL}</p>
                <p className="text-sm text-blue-200 leading-relaxed">{translation.translated_description}</p>
              </div>
            )}
          </div>
        )}

        {ev.location && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-slate-400 mb-2 flex items-center gap-1"><MapPin className="w-4 h-4" /> {t.events.location}</h3>
            <div className="bg-slate-800/50 rounded-lg p-4 flex flex-wrap gap-4 text-sm text-slate-300">
              {ev.location.city && <span>{t.events.city}: <strong>{ev.location.city}</strong></span>}
              {ev.location.region && <span>{t.events.region}: <strong>{ev.location.region}</strong></span>}
              {ev.location.road && <span>{t.events.road}: <strong>{ev.location.road}</strong></span>}
              {ev.location.latitude && <span>{t.events.coordinates}: <strong>{ev.location.latitude}, {ev.location.longitude}</strong></span>}
            </div>
          </div>
        )}

        {(ev.location_detail || ev.cargo_type || ev.modus_operandi || ev.vehicle_country || ev.financial_impact_eur) && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-slate-400 mb-2">{t.events.articleDetails}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {ev.location_detail && (
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">{t.events.locationDetail}</div>
                  <div className="text-sm text-white">{ev.location_detail}</div>
                </div>
              )}
              {ev.cargo_type && (
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">{t.events.cargoType}</div>
                  <div className="text-sm text-white capitalize">{ev.cargo_type.replace(/_/g, ' ')}</div>
                </div>
              )}
              {ev.financial_impact_eur && (
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">{t.events.estimatedLoss}</div>
                  <div className="text-sm text-white font-medium">{new Intl.NumberFormat('pl-PL', { style: 'currency', currency: 'EUR' }).format(ev.financial_impact_eur)}</div>
                </div>
              )}
              {ev.modus_operandi && (
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">{t.events.modusOperandi}</div>
                  <div className="text-sm text-white capitalize">{ev.modus_operandi.replace(/_/g, ' ')}</div>
                </div>
              )}
              {ev.vehicle_country && (
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">{t.events.vehicleCountry}</div>
                  <div className="text-sm text-white">{COUNTRIES[ev.vehicle_country]?.flag} {COUNTRIES[ev.vehicle_country]?.name || ev.vehicle_country}</div>
                </div>
              )}
            </div>
          </div>
        )}

        {ev.tags?.length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-slate-400 mb-2">{t.events.tags}</h3>
            <div className="flex flex-wrap gap-2">
              {ev.tags.map((tag) => (
                <span key={tag} className="px-2.5 py-1 bg-slate-800 border border-slate-600 rounded-full text-xs text-slate-300">{tag}</span>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 text-xs text-slate-500 pt-4 border-t border-slate-700">
          <span>{t.events.source}: {ev.source_name}</span>
        </div>
      </div>
    </div>
  )
}
