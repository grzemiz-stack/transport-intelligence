import { Component, useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'
import { MapPin } from 'lucide-react'
import { fetchDashboardMap } from '../../api/client'
import { SEVERITY_COLORS } from '../../utils/constants'
import t from '../../utils/translations'

function InvalidateSize() {
  const map = useMap()
  useEffect(() => {
    const timer = setTimeout(() => map.invalidateSize(), 200)
    return () => clearTimeout(timer)
  }, [map])
  return null
}

function EmptyMapMessage() {
  return (
    <div className="absolute inset-0 flex items-center justify-center z-[1000] pointer-events-none">
      <div className="bg-slate-900/80 rounded-lg px-4 py-3 text-center">
        <MapPin className="w-6 h-6 text-slate-500 mx-auto mb-2" />
        <p className="text-sm text-slate-400">{t.empty.noHotspots}</p>
      </div>
    </div>
  )
}

class MapErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  componentDidCatch(error, info) {
    console.error('[RiskMap error]', error, info?.componentStack)
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 flex items-center justify-center h-full">
          <div className="text-center">
            <MapPin className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-sm text-slate-500">{t.map.mapCouldNotLoad}</p>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function LeafletMap({ hotspots }) {
  return (
    <MapContainer
      center={[50.5, 10.0]}
      zoom={4}
      zoomControl={true}
      scrollWheelZoom={true}
      style={{ width: '100%', height: '100%' }}
    >
      <InvalidateSize />
      <TileLayer
        attribution='&copy; <a href="https://carto.com">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {hotspots.map((spot, i) => {
        const color = SEVERITY_COLORS[spot.severity] || '#64748b'
        return (
          <CircleMarker
            key={i}
            center={[spot.lat, spot.lng]}
            radius={Math.max(8, (spot.event_count || 1) * 1.3)}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.4, weight: 2 }}
          >
            <Popup>
              <div className="min-w-[160px]">
                <div className="font-semibold text-sm mb-1">{spot.name}</div>
                <div className="text-xs space-y-0.5">
                  <div>{t.map.popupCountry}: <strong>{spot.country}</strong></div>
                  <div>{t.map.popupSeverity}: <strong style={{ color }}>{t.severity[spot.severity] || spot.severity}</strong></div>
                  <div>{t.map.popupEvents}: <strong>{spot.event_count}</strong></div>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}

export default function RiskMap({ hotspots: propHotspots }) {
  const [hotspots, setHotspots] = useState(propHotspots || [])
  const [loading, setLoading] = useState(!propHotspots)

  useEffect(() => {
    const mapHotspot = (h) => ({
      lat: h.lat ?? h.latitude, lng: h.lng ?? h.longitude,
      name: h.name || h.label || '', country: h.country || '', type: h.type || h.event_type,
      event_count: h.event_count, severity: h.severity,
    })
    if (propHotspots) {
      setHotspots(propHotspots.map(mapHotspot))
      setLoading(false)
      return
    }
    fetchDashboardMap()
      .then((res) => setHotspots((res.data?.hotspots || []).map(mapHotspot)))
      .catch(() => setHotspots([]))
      .finally(() => setLoading(false))
  }, [propHotspots])

  return (
    <div
      className="bg-[#1e293b] rounded-xl border border-slate-700"
      style={{ position: 'relative', minHeight: 340, height: 400, overflow: 'hidden' }}
    >
      {loading ? (
        <div className="flex items-center justify-center h-full">
          <div className="animate-spin w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full" />
        </div>
      ) : (
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
          <MapErrorBoundary>
            <LeafletMap hotspots={hotspots} />
            {hotspots.length === 0 && <EmptyMapMessage />}
          </MapErrorBoundary>
        </div>
      )}
    </div>
  )
}
