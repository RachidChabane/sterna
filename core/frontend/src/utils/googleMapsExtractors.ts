/**
 * Google Maps Results Extractors
 *
 * Utilities for extracting location data from Google Maps API tool executions
 * and converting them to a format compatible with the LocationsMap component.
 */

interface LocationData {
  title: string
  address?: string
  coordinates: {
    latitude: number
    longitude: number
  }
  rating?: number | null
  phone_number?: string | null
  id?: string
  types?: string[]
}

/**
 * Extract location from geocode_address tool result
 */
export const extractGeocodeLocations = (execution: any): LocationData[] | null => {
  let result = execution.result

  // Extract nested result
  if (result && typeof result === 'object' && 'result' in result) {
    result = result.result
  }

  // Parse if string
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch (e) {
      return null
    }
  }

  if (result && result.success && result.results && result.results.length > 0) {
    // Convert geocoding results to location format
    return result.results.map((loc: any) => ({
      title: loc.formatted_address,
      address: loc.formatted_address,
      coordinates: {
        latitude: loc.latitude,
        longitude: loc.longitude
      },
      rating: null,
      phone_number: null,
      id: loc.place_id
    }))
  }

  return null
}

/**
 * Extract locations from search_nearby_places tool result
 */
export const extractNearbyPlaces = (execution: any): LocationData[] | null => {
  let result = execution.result

  // Extract nested result
  if (result && typeof result === 'object' && 'result' in result) {
    result = result.result
  }

  // Parse if string
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch (e) {
      return null
    }
  }

  if (result && result.success && result.results && result.results.length > 0) {
    // Convert nearby places to location format
    return result.results.map((place: any) => ({
      title: place.name,
      address: place.address || place.vicinity || place.formatted_address,
      coordinates: {
        latitude: place.location?.lat || place.latitude,
        longitude: place.location?.lng || place.longitude
      },
      rating: place.rating,
      phone_number: place.phone_number,
      id: place.place_id,
      types: place.types
    }))
  }

  return null
}

/**
 * Extract directions/route from get_directions tool result
 */
export const extractDirections = (execution: any) => {
  let result = execution.result

  // Extract nested result
  if (result && typeof result === 'object' && 'result' in result) {
    result = result.result
  }

  // Parse if string
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch (e) {
      return null
    }
  }

  if (result && result.success && result.routes && result.routes.length > 0) {
    const route = result.routes[0] // Get first route
    return {
      summary: route.summary,
      distance: route.distance,
      duration: route.duration,
      start_address: route.start_address,
      end_address: route.end_address,
      polyline: route.polyline,
      steps: route.steps
    }
  }

  return null
}
