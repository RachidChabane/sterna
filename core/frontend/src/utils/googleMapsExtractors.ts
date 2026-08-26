/**
 * Google Maps Results Extractors
 *
 * Utilities for extracting location data from Google Maps API tool executions
 * and converting them to a format compatible with the LocationsMap component.
 */
import { isRecord } from '@/components/models/tool-renderers/shared'

/** A tool execution's raw payload — the shape every extractor unwraps before reading fields. */
export interface ToolExecutionLike {
  result: unknown
}

export interface LocationData {
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

export interface DirectionsData {
  summary: string
  distance: string
  duration: string
  start_address: string
  end_address: string
  polyline: string
  steps: Array<{ instruction: string; distance: string; duration: string }>
}

/** One entry in a geocode_address `results` array — the fields this extractor reads. */
interface GeocodeResultItem {
  formatted_address?: string
  latitude?: number
  longitude?: number
  place_id?: string
}

const isGeocodeResultItem = (val: unknown): val is GeocodeResultItem => isRecord(val)

/** One entry in a search_nearby_places `results` array — the fields this extractor reads. */
interface NearbyPlaceItem {
  name?: string
  address?: string
  vicinity?: string
  formatted_address?: string
  location?: { lat?: number; lng?: number }
  latitude?: number
  longitude?: number
  rating?: number | null
  phone_number?: string | null
  place_id?: string
  types?: string[]
}

const isNearbyPlaceItem = (val: unknown): val is NearbyPlaceItem => isRecord(val)

/** One entry in a get_directions route's `steps` array — the fields this extractor reads. */
interface DirectionsStepItem {
  instruction?: string
  distance?: string
  duration?: string
}

const isDirectionsStepItem = (val: unknown): val is DirectionsStepItem => isRecord(val)

/** A get_directions route entry — the fields this extractor reads. */
interface RouteItem {
  summary?: string
  distance?: string
  duration?: string
  start_address?: string
  end_address?: string
  polyline?: string
  steps?: unknown
}

const isRouteItem = (val: unknown): val is RouteItem => isRecord(val)

/**
 * Unwraps a tool execution's possibly-nested, possibly-JSON-string `result`
 * payload into a plain object, or `undefined` if it isn't one.
 */
const unwrapResult = (execution: ToolExecutionLike): Record<string, unknown> | undefined => {
  let result: unknown = execution.result

  if (isRecord(result) && 'result' in result) {
    result = result.result
  }

  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch {
      return undefined
    }
  }

  return isRecord(result) ? result : undefined
}

/**
 * Extract location from geocode_address tool result
 */
export const extractGeocodeLocations = (execution: ToolExecutionLike): LocationData[] | null => {
  const result = unwrapResult(execution)
  if (!result || !result.success || !Array.isArray(result.results) || result.results.length === 0) {
    return null
  }

  return result.results.filter(isGeocodeResultItem).map((loc) => ({
    title: loc.formatted_address ?? '',
    address: loc.formatted_address,
    coordinates: {
      latitude: loc.latitude ?? 0,
      longitude: loc.longitude ?? 0,
    },
    rating: null,
    phone_number: null,
    id: loc.place_id,
  }))
}

/**
 * Extract locations from search_nearby_places tool result
 */
export const extractNearbyPlaces = (execution: ToolExecutionLike): LocationData[] | null => {
  const result = unwrapResult(execution)
  if (!result || !result.success || !Array.isArray(result.results) || result.results.length === 0) {
    return null
  }

  return result.results.filter(isNearbyPlaceItem).map((place) => ({
    title: place.name ?? '',
    address: place.address || place.vicinity || place.formatted_address,
    coordinates: {
      latitude: place.location?.lat ?? place.latitude ?? 0,
      longitude: place.location?.lng ?? place.longitude ?? 0,
    },
    rating: place.rating,
    phone_number: place.phone_number,
    id: place.place_id,
    types: place.types,
  }))
}

/**
 * Extract directions/route from get_directions tool result
 */
export const extractDirections = (execution: ToolExecutionLike): DirectionsData | null => {
  const result = unwrapResult(execution)
  if (!result || !result.success || !Array.isArray(result.routes) || result.routes.length === 0) {
    return null
  }

  const route = result.routes[0] // Get first route
  if (!isRouteItem(route)) return null

  const steps = Array.isArray(route.steps) ? route.steps.filter(isDirectionsStepItem) : []

  return {
    summary: route.summary ?? '',
    distance: route.distance ?? '',
    duration: route.duration ?? '',
    start_address: route.start_address ?? '',
    end_address: route.end_address ?? '',
    polyline: route.polyline ?? '',
    steps: steps.map((s) => ({
      instruction: s.instruction ?? '',
      distance: s.distance ?? '',
      duration: s.duration ?? '',
    })),
  }
}
