/**
 * DirectionsMap Component
 *
 * Displays a Google Maps route with directions, using encoded polyline.
 * Shows start/end markers and route path.
 */

import { useMemo, useState, useEffect } from 'react'
import { GoogleMap, useJsApiLoader, Polyline, Marker, InfoWindow } from '@react-google-maps/api'
import { Navigation } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { darkMapStyles, lightMapStyles } from '@/utils/googleMapsTheme'

interface DirectionsData {
  summary: string
  distance: string
  duration: string
  start_address: string
  end_address: string
  polyline: string
  steps: Array<{
    instruction: string
    distance: string
    duration: string
  }>
}

interface DirectionsMapProps {
  directions: DirectionsData
  title?: string
}

const mapContainerStyle = {
  width: '100%',
  height: '500px',
  borderRadius: '0.5rem'
}

// Decode Google Maps encoded polyline
function decodePolyline(encoded: string): google.maps.LatLngLiteral[] {
  const poly: google.maps.LatLngLiteral[] = []
  let index = 0
  const len = encoded.length
  let lat = 0
  let lng = 0

  while (index < len) {
    let b: number
    let shift = 0
    let result = 0
    do {
      b = encoded.charCodeAt(index++) - 63
      result |= (b & 0x1f) << shift
      shift += 5
    } while (b >= 0x20)
    const dlat = result & 1 ? ~(result >> 1) : result >> 1
    lat += dlat

    shift = 0
    result = 0
    do {
      b = encoded.charCodeAt(index++) - 63
      result |= (b & 0x1f) << shift
      shift += 5
    } while (b >= 0x20)
    const dlng = result & 1 ? ~(result >> 1) : result >> 1
    lng += dlng

    poly.push({ lat: lat / 1e5, lng: lng / 1e5 })
  }

  return poly
}

export function DirectionsMap({ directions, title }: DirectionsMapProps) {
  const [selectedMarker, setSelectedMarker] = useState<'start' | 'end' | null>(null)
  const [map, setMap] = useState<google.maps.Map | null>(null)
  const { isDark } = useTheme()

  // Load Google Maps API
  const { isLoaded, loadError } = useJsApiLoader({
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '',
    libraries: ['places']
  })

  // Decode polyline to path
  const path = useMemo(() => {
    if (!isLoaded || !directions.polyline) return []
    return decodePolyline(directions.polyline)
  }, [directions.polyline, isLoaded])

  // Get start and end coordinates
  const startPoint = path.length > 0 ? path[0] : null
  const endPoint = path.length > 0 ? path[path.length - 1] : null

  // Calculate center
  const center = useMemo(() => {
    if (path.length === 0) return { lat: 48.8566, lng: 2.3522 }
    if (!isLoaded || typeof google === 'undefined') return { lat: 48.8566, lng: 2.3522 }

    const bounds = new google.maps.LatLngBounds()
    path.forEach(point => bounds.extend(point))
    const centerPoint = bounds.getCenter()
    return { lat: centerPoint.lat(), lng: centerPoint.lng() }
  }, [path, isLoaded])

  // Fit bounds when map loads
  useEffect(() => {
    if (map && path.length > 0 && isLoaded && typeof google !== 'undefined') {
      const bounds = new google.maps.LatLngBounds()
      path.forEach(point => bounds.extend(point))
      map.fitBounds(bounds)
    }
  }, [map, path, isLoaded])

  // Update map styles when theme changes
  useEffect(() => {
    if (map && isLoaded) {
      map.setOptions({
        styles: isDark ? darkMapStyles : lightMapStyles
      })
    }
  }, [map, isDark, isLoaded])

  if (loadError) {
    return (
      <div className="w-full p-4 border border-border rounded-lg bg-muted/30">
        <div className="flex items-center gap-2 text-red-500">
          <Navigation className="h-4 w-4" />
          <span className="text-sm">Error loading map. Please check your Google Maps API key.</span>
        </div>
      </div>
    )
  }

  if (!isLoaded) {
    return (
      <div className="w-full p-4 border border-border rounded-lg bg-muted/30 animate-pulse">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Navigation className="h-4 w-4" />
          <span className="text-sm">Loading map...</span>
        </div>
      </div>
    )
  }

  if (path.length === 0) {
    return (
      <div className="w-full p-4 border border-border rounded-lg bg-muted/30">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Navigation className="h-4 w-4" />
          <span className="text-sm">No route data available.</span>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full space-y-3">
      {/* Route summary */}
      <div className="flex items-start gap-3 p-3 border border-border/40 rounded-lg bg-background/50">
        <Navigation className="h-4 w-4 text-accent-brand mt-0.5 flex-shrink-0" />
        <div className="flex-1 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold">{directions.summary}</span>
            <span className="text-xs text-muted-foreground">•</span>
            <span className="text-xs font-medium text-accent-brand">{directions.distance}</span>
            <span className="text-xs text-muted-foreground">•</span>
            <span className="text-xs text-muted-foreground">{directions.duration}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            <div className="flex items-start gap-1">
              <span className="flex-shrink-0">From:</span>
              <span className="flex-1">{directions.start_address}</span>
            </div>
            <div className="flex items-start gap-1">
              <span className="flex-shrink-0">To:</span>
              <span className="flex-1">{directions.end_address}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Map */}
      <div className="w-full border border-border/40 rounded-lg overflow-hidden shadow-sm">
        <GoogleMap
          mapContainerStyle={mapContainerStyle}
          center={center}
          zoom={10}
          onLoad={setMap}
          options={{
            streetViewControl: false,
            mapTypeControl: false,
            fullscreenControl: true,
            zoomControl: true,
            styles: isDark ? darkMapStyles : lightMapStyles
          }}
        >
          {/* Route polyline */}
          <Polyline
            path={path}
            options={{
              strokeColor: '#3d5ce4',
              strokeOpacity: 1,
              strokeWeight: 4
            }}
          />

          {/* Start marker */}
          {startPoint && (
            <Marker
              position={startPoint}
              onClick={() => setSelectedMarker('start')}
              icon={{
                path: google.maps.SymbolPath.CIRCLE,
                fillColor: '#22c55e',
                fillOpacity: 1,
                strokeColor: '#ffffff',
                strokeWeight: 3,
                scale: 10
              }}
              label={{
                text: 'A',
                color: '#ffffff',
                fontSize: '12px',
                fontWeight: 'bold'
              }}
            />
          )}

          {/* End marker */}
          {endPoint && (
            <Marker
              position={endPoint}
              onClick={() => setSelectedMarker('end')}
              icon={{
                path: google.maps.SymbolPath.CIRCLE,
                fillColor: '#ef4444',
                fillOpacity: 1,
                strokeColor: '#ffffff',
                strokeWeight: 3,
                scale: 10
              }}
              label={{
                text: 'B',
                color: '#ffffff',
                fontSize: '12px',
                fontWeight: 'bold'
              }}
            />
          )}

          {/* Info windows */}
          {selectedMarker === 'start' && startPoint && (
            <InfoWindow
              position={startPoint}
              onCloseClick={() => setSelectedMarker(null)}
            >
              <div className="p-2">
                <h3 className="font-semibold text-sm mb-1">Start</h3>
                <p className="text-xs text-gray-600">{directions.start_address}</p>
              </div>
            </InfoWindow>
          )}

          {selectedMarker === 'end' && endPoint && (
            <InfoWindow
              position={endPoint}
              onCloseClick={() => setSelectedMarker(null)}
            >
              <div className="p-2">
                <h3 className="font-semibold text-sm mb-1">Destination</h3>
                <p className="text-xs text-gray-600">{directions.end_address}</p>
              </div>
            </InfoWindow>
          )}
        </GoogleMap>
      </div>
    </div>
  )
}
