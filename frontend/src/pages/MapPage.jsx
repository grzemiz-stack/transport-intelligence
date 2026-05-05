import { Component, useState, useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, Polyline, FeatureGroup, LayersControl, useMap } from 'react-leaflet'
import { MapPin } from 'lucide-react'
import { fetchDashboardMap } from '../api/client'
import { SEVERITY_COLORS } from '../utils/constants'
import t from '../utils/translations'

const CORRIDORS = [
  { name: 'Morze Północne-Bałtyk', color: '#3b82f6', points: [[51.90, 4.48], [52.52, 13.40], [52.34, 14.69], [52.23, 21.01]] },
  { name: 'Ren-Alpy',               color: '#22c55e', points: [[51.90, 4.48], [51.43, 6.76], [47.04, 11.51], [45.46, 9.19]] },
  { name: 'Orient-Śródziemnomorski', color: '#f97316', points: [[52.52, 13.40], [50.08, 14.44], [47.50, 19.04], [46.18, 21.32]] },
  { name: 'Śródziemnomorski',        color: '#eab308', points: [[41.39, 2.17], [43.30, 5.37], [45.46, 9.19]] },
]

function InvalidateSize() {
  const map = useMap()
  useEffect(() => {
    map.invalidateSize()
    const timer = setTimeout(() => map.invalidateSize(), 300)
    return () => clearTimeout(timer)
  }, [map])
  return null
}

function FlyTo({ lat, lng }) {
  const map = useMap()
  useEffect(() => {
    if (typeof lat === 'number' && typeof lng === 'number') {
      map.flyTo([lat, lng], 8, { duration: 0.8 })
    }
  }, [lat, lng, map])
  return null
}

function MapFallback() {
  return (
    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: '#0f172a', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
      <MapPin style={{ width: 64, height: 64, marginBottom: 16, color: '#334155' }} />
      <div style={{ fontSize: 18, fontWeight: 600, color: '#94a3b8' }}>{t.map.mapCouldNotLoad}</div>
      <div style={{ fontSize: 14, marginTop: 4 }}>{t.map.checkConsole}</div>
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
    console.error('[MapPage error]', error, info?.componentStack)
  }
  render() {
    if (this.state.hasError) return <MapFallback />
    return this.props.children
  }
}

function FullMap({ hotspots, flyTarget }) {
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

      {flyTarget && <FlyTo lat={flyTarget.lat} lng={flyTarget.lng} />}

      <LayersControl position="topright">
        <LayersControl.Overlay checked name={t.map.hotspots}>
          <FeatureGroup>
            {hotspots.map((spot, i) => {
              const color = SEVERITY_COLORS[spot.severity] || '#64748b'
              return (
                <CircleMarker
                  key={`hs-${i}`}
                  center={[spot.lat, spot.lng]}
                  radius={Math.max(8, (spot.event_count || 1) * 1.3)}
                  pathOptions={{ color, fillColor: color, fillOpacity: 0.35, weight: 2 }}
                >
                  <Popup>
                    <div style={{ minWidth: 180 }}>
                      <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{spot.name}</div>
                      <div style={{ fontSize: 12, lineHeight: 1.6 }}>
                        <div>{t.map.popupCountry}: <strong>{spot.country}</strong></div>
                        <div>{t.map.popupSeverity}: <strong style={{ color }}>{t.severity[spot.severity] || spot.severity}</strong></div>
                        <div>{t.map.popupEvents}: <strong>{spot.event_count}</strong></div>
                        {spot.type && <div>{t.map.popupType}: {t.eventTypes[spot.type] || spot.type}</div>}
                      </div>
                    </div>
                  </Popup>
                </CircleMarker>
              )
            })}
          </FeatureGroup>
        </LayersControl.Overlay>

        <LayersControl.Overlay checked name={t.map.corridors}>
          <FeatureGroup>
            {CORRIDORS.map((c, i) => (
              <Polyline
                key={`corr-${i}`}
                positions={c.points}
                pathOptions={{ color: c.color, weight: 2.5, opacity: 0.6, dashArray: '8 4' }}
              >
                <Popup>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{c.name}</div>
                </Popup>
              </Polyline>
            ))}
          </FeatureGroup>
        </LayersControl.Overlay>
      </LayersControl>
    </MapContainer>
  )
}

export default function MapPage() {
  const [hotspots, setHotspots] = useState([])
  const [loading, setLoading] = useState(true)
  const [flyTarget, setFlyTarget] = useState(null)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    fetchDashboardMap()
      .then((res) => {
        const raw = res.data?.hotspots || []
        setHotspots(raw.map(h => ({
          lat: h.lat ?? h.latitude, lng: h.lng ?? h.longitude,
          name: h.name || h.label || '', country: h.country || '', type: h.type || h.event_type,
          event_count: h.event_count, severity: h.severity,
        })))
      })
      .catch(() => setHotspots([]))
      .finally(() => setLoading(false))
  }, [])

  const handleClick = (hs) => {
    setSelected(hs.name)
    setFlyTarget({ lat: hs.lat, lng: hs.lng })
  }

  return (
    <div style={{
      display: 'flex',
      height: 'calc(100vh - 64px)',
      width: 'calc(100% + 48px)',
      margin: '-24px',
      overflow: 'hidden',
    }}>
      {/* Sidebar */}
      <div style={{
        width: '350px',
        flexShrink: 0,
        overflowY: 'auto',
        background: '#1e293b',
        borderRight: '1px solid #334155',
        padding: '16px',
      }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#fff', marginBottom: 16 }}>{t.map.title}</h2>

        {/* Legend */}
        <div style={{ marginBottom: 16, padding: 12, background: 'rgba(30,41,59,0.5)', borderRadius: 8 }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8, fontWeight: 500 }}>{t.map.severity}</div>
          {Object.entries(SEVERITY_COLORS).map(([level, color]) => (
            <div key={level} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, marginBottom: 4 }}>
              <span style={{ width: 12, height: 12, borderRadius: '50%', background: color, flexShrink: 0 }} />
              <span style={{ color: '#94a3b8' }}>{t.severity[level] || level}</span>
            </div>
          ))}
          <div style={{ fontSize: 11, color: '#64748b', marginTop: 12, marginBottom: 8, fontWeight: 500 }}>{t.map.corridors}</div>
          {CORRIDORS.map((c) => (
            <div key={c.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, marginBottom: 4 }}>
              <span style={{ width: 16, height: 2, borderRadius: 1, background: c.color, flexShrink: 0 }} />
              <span style={{ color: '#94a3b8' }}>{c.name}</span>
            </div>
          ))}
        </div>

        {/* Hotspot list */}
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full" />
          </div>
        ) : hotspots.length === 0 ? (
          <div style={{ padding: '24px 0', textAlign: 'center' }}>
            <p style={{ fontSize: 13, color: '#64748b' }}>{t.empty.noHotspots}</p>
          </div>
        ) : (
          <>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8, fontWeight: 500 }}>
              {t.map.hotspots} ({hotspots.length})
            </div>
            {[...hotspots]
              .sort((a, b) => (b.event_count || 0) - (a.event_count || 0))
              .map((hs, i) => (
                <button
                  key={i}
                  onClick={() => handleClick(hs)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: '10px 12px',
                    marginBottom: 6,
                    borderRadius: 8,
                    border: selected === hs.name ? '1px solid rgba(59,130,246,0.3)' : '1px solid transparent',
                    background: selected === hs.name ? 'rgba(59,130,246,0.15)' : 'rgba(30,41,59,0.5)',
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 13, color: '#fff', fontWeight: 500 }}>{hs.name}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: SEVERITY_COLORS[hs.severity] }}>
                      {hs.event_count}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{hs.country}{hs.type ? ` — ${t.eventTypes[hs.type] || hs.type}` : ''}</div>
                </button>
              ))}
          </>
        )}
      </div>

      {/* Map container */}
      <div style={{
        flex: '1 1 0%',
        position: 'relative',
        minWidth: '400px',
        overflow: 'hidden',
      }}>
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
          <MapErrorBoundary>
            <FullMap hotspots={hotspots} flyTarget={flyTarget} />
          </MapErrorBoundary>
        </div>
      </div>
    </div>
  )
}
