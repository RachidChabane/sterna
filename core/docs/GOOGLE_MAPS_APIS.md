# Google Maps APIs Configuration

## Enabled APIs (9)

### Core Display
- **Maps JavaScript API** - Interactive maps with markers and info windows
- **Street View Static API** - Street-level imagery of locations

### Location Services
- **Places API (New)** - POI details, photos, reviews, ratings, opening hours
- **Geocoding API** - Convert addresses to GPS coordinates
- **Geolocation API** - Auto-detect user position

### Routing & Distance
- **Directions API** - Calculate and display routes on map
- **Distance Matrix API** - Travel time/distance between multiple points

### Environmental Data
- **Air Quality API** - Real-time air quality for locations
- **Weather API** - Weather information for contextual responses

## Key Configuration

**API Key**: `VITE_GOOGLE_MAPS_API_KEY` in `frontend/.env.development`

**Restrictions** (Dev):
- API restrictions: 9 APIs listed above
- Website restrictions: None (for development)

**Restrictions** (Prod)**:
- Enable "HTTP referrers" restriction
- Add production domain(s)
- Keep same 9 APIs

## Backend Service

**NEW**: Full-stack Google Maps integration via dedicated service

**Service**: `google-maps` (port 8005)
- FastAPI backend with Redis caching
- 9 optimized endpoints for all enabled APIs
- 5 LangChain tools for LLM integration
- 80-90% cost reduction via smart caching

**Enable in LLM**:
Google Maps tools are automatically enabled when Extended Search (Brave Search) is activated.
No separate configuration needed - just enable Extended Search in the chat UI.

**Available Tools**:
- `geocode_address` - Convert addresses to GPS
- `get_directions` - Calculate routes with steps
- `search_nearby_places` - Find POIs near location
- `get_air_quality` - Air quality index
- `get_street_view` - Street view availability

## Usage Examples

### Via LLM (Automatic)
- **"What's the Eiffel Tower address?"** → Geocoding tool
- **"How do I walk from A to B?"** → Directions tool
- **"Find restaurants near coordinates X,Y"** → Places tool
- **"Air quality in Paris?"** → Air Quality tool

### Via Frontend (Manual)
- **"Find restaurants near Eiffel Tower"** → Interactive map with POI markers + details
- **"Show me the way to X"** → Route drawn on map with directions
- **Street views** → Visual preview of locations

## Architecture

```
Frontend (React) ←→ Google Maps JS API (client-side map display)
                ↓
LLM ←→ google-maps service ←→ Redis Cache
              ↓
      Google Maps APIs (9 endpoints)
```

## Billing

- **Free tier**: $200/month (covers ~40K map loads or 40K geocoding requests)
- **With caching**: 90% cost reduction on repeated requests
- **Monitor**: [Google Cloud Console](https://console.cloud.google.com/google/maps-apis/metrics)

**Cost Examples** (with caching):
- 10K geocoding/month: ~$5-10 (vs $50 without cache)
- 5K directions/month: ~$2.50-5 (vs $25 without cache)

## Documentation

Full service documentation: `core/google-maps/README.md`
