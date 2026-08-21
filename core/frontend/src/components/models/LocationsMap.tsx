/**
 * LocationsMap Component
 *
 * Displays locations from Brave Search on an interactive Google Map.
 * Shows markers for each location with custom popup details.
 */

import { useMemo, useState, useEffect, useCallback, useRef } from 'react'
import { GoogleMap, useJsApiLoader, OverlayView } from '@react-google-maps/api'
import type { Libraries } from '@react-google-maps/api'
import { MapPin, ChevronLeft, ChevronRight, Star, X, UtensilsCrossed, Hotel, Coffee, ShoppingBag, Building2, Landmark, Car, Trees, Music, Dumbbell, GraduationCap, Stethoscope, Fuel, Plane, ExternalLink } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'
import { darkMapStyles, lightMapStyles } from '@/utils/googleMapsTheme'
import { api } from '@/api/client'

// Static libraries array to prevent useJsApiLoader from reloading
const GOOGLE_MAPS_LIBRARIES: Libraries = ['places']

// Category icon mapping
const categoryIcons: Record<string, React.ElementType> = {
  restaurant: UtensilsCrossed,
  food: UtensilsCrossed,
  cafe: Coffee,
  coffee: Coffee,
  hotel: Hotel,
  lodging: Hotel,
  shopping: ShoppingBag,
  store: ShoppingBag,
  business: Building2,
  landmark: Landmark,
  attraction: Landmark,
  museum: Landmark,
  car: Car,
  parking: Car,
  park: Trees,
  nature: Trees,
  entertainment: Music,
  nightlife: Music,
  bar: Music,
  gym: Dumbbell,
  fitness: Dumbbell,
  school: GraduationCap,
  education: GraduationCap,
  hospital: Stethoscope,
  health: Stethoscope,
  gas: Fuel,
  fuel: Fuel,
  airport: Plane,
  transit: Plane,
}

const getCategoryIcon = (category?: string): React.ElementType => {
  if (!category) return MapPin
  const normalizedCategory = category.toLowerCase()
  // Check for exact match first
  if (categoryIcons[normalizedCategory]) return categoryIcons[normalizedCategory]
  // Check for partial match
  for (const [key, icon] of Object.entries(categoryIcons)) {
    if (normalizedCategory.includes(key) || key.includes(normalizedCategory)) {
      return icon
    }
  }
  return MapPin
}

// Star rating component
const StarRating = ({ rating, maxRating = 5 }: { rating: number; maxRating?: number }) => {
  const fullStars = Math.floor(rating)
  const partialFill = rating - fullStars
  const emptyStars = maxRating - Math.ceil(rating)

  return (
    <div className="flex items-center gap-0.5">
      {/* Full stars */}
      {Array.from({ length: fullStars }).map((_, i) => (
        <Star key={`full-${i}`} className="h-3 w-3 fill-yellow-400 text-yellow-400" />
      ))}
      {/* Partial star */}
      {partialFill > 0 && (
        <div className="relative">
          <Star className="h-3 w-3 text-gray-300" />
          <div className="absolute inset-0 overflow-hidden" style={{ width: `${partialFill * 100}%` }}>
            <Star className="h-3 w-3 fill-yellow-400 text-yellow-400" />
          </div>
        </div>
      )}
      {/* Empty stars */}
      {Array.from({ length: emptyStars }).map((_, i) => (
        <Star key={`empty-${i}`} className="h-3 w-3 text-gray-300" />
      ))}
      <span className="ml-1 text-xs text-gray-600">{rating.toFixed(1)}</span>
    </div>
  )
}

interface Location {
  id?: string
  title: string
  address?: string
  coordinates?: {
    latitude: number
    longitude: number
  }
  rating?: number
  phone?: string
  opening_hours?: string
  url?: string
  thumbnail?: string
  image?: string
  icon_category?: string
}

// Fetch photo URL from Google Places API (via backend proxy).
// Uses the shared api client: the endpoint is authenticated + metered.
const fetchPlacePhoto = async (
  query: string,
  latitude?: number,
  longitude?: number
): Promise<string | null> => {
  try {
    const response = await api.post('/llm/google-maps/places/search-photo/', {
      query,
      latitude,
      longitude,
      max_width: 400
    })
    const data = response.data
    if (data.success && data.photo_url) {
      return data.photo_url
    }
    return null
  } catch (error) {
    console.error('Failed to fetch place photo:', error)
    return null
  }
}

interface LocationsMapProps {
  locations: Location[]
  title?: string
}

const mapContainerStyle = {
  width: '100%',
  height: '400px',
  borderRadius: '0.5rem'
}

const defaultCenter = {
  lat: 48.8566,
  lng: 2.3522
}

export function LocationsMap({ locations, title }: LocationsMapProps) {
  const [selectedLocation, setSelectedLocation] = useState<Location | null>(null)
  const [focusedIndex, setFocusedIndex] = useState<number>(0)
  const [map, setMap] = useState<google.maps.Map | null>(null)
  const [photoUrls, setPhotoUrls] = useState<Record<string, string | null>>({})
  const [loadingPhoto, setLoadingPhoto] = useState<string | null>(null)
  const fetchedPhotos = useRef<Set<string>>(new Set())
  const { isDark } = useTheme()

  // Filter valid locations once
  const validLocations = useMemo(() => locations.filter(loc => loc.coordinates), [locations])

  // Fetch photo when location is selected
  useEffect(() => {
    if (!selectedLocation) return

    const locationKey = selectedLocation.id || selectedLocation.title

    // Skip if already fetched or currently fetching
    if (fetchedPhotos.current.has(locationKey) || loadingPhoto === locationKey) return

    // Skip if location already has a thumbnail
    if (selectedLocation.thumbnail || selectedLocation.image) return

    fetchedPhotos.current.add(locationKey)
    setLoadingPhoto(locationKey)

    fetchPlacePhoto(
      `${selectedLocation.title} ${selectedLocation.address || ''}`,
      selectedLocation.coordinates?.latitude,
      selectedLocation.coordinates?.longitude
    ).then(url => {
      setPhotoUrls(prev => ({ ...prev, [locationKey]: url }))
      setLoadingPhoto(null)
    })
  }, [selectedLocation, loadingPhoto])

  // Load Google Maps API
  const { isLoaded, loadError } = useJsApiLoader({
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '',
    libraries: GOOGLE_MAPS_LIBRARIES
  })

  // Calculate map center from locations
  const center = useMemo(() => {
    if (validLocations.length === 0) return defaultCenter

    const avgLat = validLocations.reduce((sum, loc) => sum + (loc.coordinates?.latitude || 0), 0) / validLocations.length
    const avgLng = validLocations.reduce((sum, loc) => sum + (loc.coordinates?.longitude || 0), 0) / validLocations.length

    return { lat: avgLat, lng: avgLng }
  }, [validLocations])

  // Navigate to a specific location
  const focusLocation = useCallback((index: number) => {
    if (!map || !validLocations[index]?.coordinates) return

    const loc = validLocations[index]
    setFocusedIndex(index)
    setSelectedLocation(loc)

    map.panTo({
      lat: loc.coordinates!.latitude,
      lng: loc.coordinates!.longitude
    })
    map.setZoom(15)
  }, [map, validLocations])

  // Navigate to previous location
  const goToPrevious = useCallback(() => {
    const newIndex = focusedIndex <= 0 ? validLocations.length - 1 : focusedIndex - 1
    focusLocation(newIndex)
  }, [focusedIndex, validLocations.length, focusLocation])

  // Navigate to next location
  const goToNext = useCallback(() => {
    const newIndex = focusedIndex >= validLocations.length - 1 ? 0 : focusedIndex + 1
    focusLocation(newIndex)
  }, [focusedIndex, validLocations.length, focusLocation])

  // Handle map load
  const onLoad = (map: google.maps.Map) => {
    if (!isLoaded || typeof google === 'undefined') return

    setMap(map)

    // Fit bounds to show all markers
    if (validLocations.length > 0) {
      const bounds = new google.maps.LatLngBounds()
      validLocations.forEach(loc => {
        if (loc.coordinates) {
          bounds.extend({ lat: loc.coordinates.latitude, lng: loc.coordinates.longitude })
        }
      })
      map.fitBounds(bounds)
    }
  }

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
          <MapPin className="h-4 w-4" />
          <span className="text-sm">Error loading map. Please check your Google Maps API key.</span>
        </div>
      </div>
    )
  }

  if (!isLoaded) {
    return (
      <div className="w-full p-4 border border-border rounded-lg bg-muted/30 animate-pulse">
        <div className="flex items-center gap-2 text-muted-foreground">
          <MapPin className="h-4 w-4" />
          <span className="text-sm">Loading map...</span>
        </div>
      </div>
    )
  }

  if (validLocations.length === 0) {
    return (
      <div className="w-full p-4 border border-border rounded-lg bg-muted/30">
        <div className="flex items-center gap-2 text-muted-foreground">
          <MapPin className="h-4 w-4" />
          <span className="text-sm">No location coordinates available to display on map.</span>
        </div>
      </div>
    )
  }

  const showNavigation = validLocations.length > 1

  return (
    <div className="w-full space-y-2">
      {/* Header with title and navigation */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          {title && (
            <>
              <MapPin className="h-3.5 w-3.5 text-accent-brand" />
              <span className="text-xs font-medium text-muted-foreground">{title}</span>
            </>
          )}
        </div>

        {/* Navigation controls */}
        {showNavigation && (
          <div className="flex items-center gap-1">
            <button
              onClick={goToPrevious}
              className="p-1 rounded hover:bg-accent-brand/10 text-muted-foreground hover:text-accent-brand transition-colors"
              title="Previous location"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-xs text-muted-foreground min-w-[3rem] text-center">
              {focusedIndex + 1} / {validLocations.length}
            </span>
            <button
              onClick={goToNext}
              className="p-1 rounded hover:bg-accent-brand/10 text-muted-foreground hover:text-accent-brand transition-colors"
              title="Next location"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {/* Current location name */}
      {showNavigation && validLocations[focusedIndex] && (
        <div className="px-1">
          <span className="text-xs font-medium text-foreground/80">
            {validLocations[focusedIndex].title}
          </span>
          {validLocations[focusedIndex].address && (
            <span className="text-xs text-muted-foreground ml-2">
              {validLocations[focusedIndex].address}
            </span>
          )}
        </div>
      )}

      <div className="w-full border border-border/40 rounded-lg overflow-hidden shadow-sm relative">
        <GoogleMap
          mapContainerStyle={mapContainerStyle}
          center={center}
          zoom={13}
          onLoad={onLoad}
          options={{
            streetViewControl: false,
            mapTypeControl: false,
            fullscreenControl: true,
            zoomControl: true,
            clickableIcons: true,
            styles: isDark ? darkMapStyles : lightMapStyles
          }}
        >
          {/* Custom markers using OverlayView to avoid deprecated google.maps.Marker */}
          {validLocations.map((location, index) => {
            const isFocused = index === focusedIndex
            return (
              <OverlayView
                key={location.id || index}
                position={{
                  lat: location.coordinates!.latitude,
                  lng: location.coordinates!.longitude
                }}
                mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
              >
                <button
                  onClick={() => {
                    setFocusedIndex(index)
                    setSelectedLocation(location)
                  }}
                  className="transform -translate-x-1/2 -translate-y-1/2 cursor-pointer transition-all duration-200 hover:scale-110"
                  style={{ zIndex: isFocused ? 1000 : index }}
                >
                  <div
                    className={`rounded-full border-2 ${
                      isFocused
                        ? 'bg-accent-brand border-white shadow-lg'
                        : 'bg-slate-500 border-slate-400 hover:bg-slate-400'
                    }`}
                    style={{
                      width: isFocused ? 20 : 14,
                      height: isFocused ? 20 : 14,
                    }}
                  />
                </button>
              </OverlayView>
            )
          })}

          {selectedLocation && selectedLocation.coordinates && (() => {
            const locationKey = selectedLocation.id || selectedLocation.title
            const fetchedPhotoUrl = photoUrls[locationKey]
            const photoUrl = selectedLocation.thumbnail || selectedLocation.image || fetchedPhotoUrl
            const isLoadingPhoto = loadingPhoto === locationKey
            const CategoryIcon = getCategoryIcon(selectedLocation.icon_category)

            return (
              <OverlayView
                position={{
                  lat: selectedLocation.coordinates.latitude,
                  lng: selectedLocation.coordinates.longitude
                }}
                mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}
              >
                <div
                  className="relative -translate-x-1/2 -translate-y-full mb-3"
                  style={{ width: 280 }}
                >
                  {/* Popup card */}
                  <div className="relative bg-card border border-border rounded-lg overflow-hidden shadow-lg">
                    {/* Image - clickable to open in Google Maps */}
                    <a
                      href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
                        selectedLocation.coordinates
                          ? `${selectedLocation.coordinates.latitude},${selectedLocation.coordinates.longitude}`
                          : `${selectedLocation.title} ${selectedLocation.address || ''}`
                      )}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="relative block w-full h-32 bg-muted cursor-pointer group"
                    >
                      {isLoadingPhoto ? (
                        <div className="absolute inset-0 animate-pulse flex items-center justify-center">
                          <CategoryIcon className="h-8 w-8 text-muted-foreground/40" />
                        </div>
                      ) : photoUrl ? (
                        <img
                          src={photoUrl}
                          alt={selectedLocation.title}
                          className="w-full h-full object-cover"
                          referrerPolicy="no-referrer"
                        />
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center bg-muted">
                          <CategoryIcon className="h-10 w-10 text-muted-foreground/30" />
                        </div>
                      )}
                      {/* Hover overlay */}
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                        <span className="text-white text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                          Open in Google Maps
                        </span>
                      </div>
                      {/* Rating badge */}
                      {selectedLocation.rating && (
                        <div className="absolute bottom-2 left-2 flex items-center gap-1 bg-background/90 backdrop-blur-sm px-2 py-0.5 rounded-full">
                          <Star className="h-3 w-3 fill-yellow-500 text-yellow-500" />
                          <span className="text-xs font-medium text-foreground">{selectedLocation.rating.toFixed(1)}</span>
                        </div>
                      )}
                    </a>
                    {/* Close button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedLocation(null)
                      }}
                      className="absolute top-2 right-2 p-1 rounded-full bg-background/80 hover:bg-background text-muted-foreground hover:text-foreground transition-colors z-10"
                    >
                      <X className="h-4 w-4" />
                    </button>
                    {/* Content */}
                    <div className="p-3 space-y-1">
                      <h3 className="font-medium text-sm text-foreground leading-snug">{selectedLocation.title}</h3>
                      {selectedLocation.address && (
                        <p className="text-xs text-muted-foreground">{selectedLocation.address}</p>
                      )}
                      {(selectedLocation.phone || selectedLocation.url) && (
                        <div className="flex items-center justify-between pt-1">
                          {selectedLocation.phone && (
                            <span className="text-xs text-muted-foreground">{selectedLocation.phone}</span>
                          )}
                          {selectedLocation.url && (
                            <a
                              href={selectedLocation.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-xs text-accent-brand hover:underline"
                            >
                              Details <ExternalLink className="h-3 w-3" />
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  {/* Arrow pointing to marker */}
                  <div className="absolute left-1/2 -translate-x-1/2 -bottom-2">
                    <div className="w-4 h-4 rotate-45 bg-card border-r border-b border-border" />
                  </div>
                </div>
              </OverlayView>
            )
          })()}
        </GoogleMap>
      </div>
    </div>
  )
}
