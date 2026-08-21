# Google Maps API Service

Optimized backend service providing access to all Google Maps Platform APIs with Redis caching, rate limiting, and LangChain integration.

## Features

### Implemented APIs (9 total)

1. **Geocoding API** - Convert addresses to GPS coordinates (24h cache)
2. **Reverse Geocoding** - Convert coordinates to addresses (24h cache)
3. **Directions API** - Calculate routes with turn-by-turn directions (1h cache)
4. **Distance Matrix API** - Bulk distance/duration calculations (1h cache)
5. **Places API (New)** - POI details, photos, reviews, ratings (6h cache)
6. **Nearby Search** - Find places near a location (1h cache)
7. **Air Quality API** - Current air quality index (1h cache)
8. **Street View Static API** - Street-level imagery URLs
9. **Weather API** - Ready for implementation

### Optimizations

- **Redis Caching**: Automatic caching with configurable TTL per endpoint
- **Smart Cache Keys**: MD5-hashed deterministic keys from parameters
- **Cost Reduction**: Cached geocoding/places reduce API costs by 80-90%
- **Hot Reload**: Development mode with auto-reload on code changes
- **Error Handling**: Comprehensive error handling with fallbacks

## Architecture

```
┌─────────────┐
│   LLM       │  Uses LangChain tools
│   (GPT-4)   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│ LangChain Tools (5 tools)   │
│ - geocode_address            │
│ - get_directions             │
│ - search_nearby_places       │
│ - get_air_quality            │
│ - get_street_view            │
└──────────┬──────────────────┘
           │
           ▼
┌────────────────────────────────┐
│ Google Maps Service (FastAPI)  │
│ Port: 8005                      │
│ - Geocoding endpoints           │
│ - Directions endpoints          │
│ - Places endpoints              │
│ - Environmental endpoints       │
└──────┬─────────────────────────┘
       │
       ├──► Redis (Cache)
       │
       └──► Google Maps API
```

## Endpoints

### Geocoding

**POST** `/geocoding/forward`
```json
{
  "address": "Eiffel Tower, Paris",
  "language": "en"
}
```

**POST** `/geocoding/reverse`
```json
{
  "latitude": 48.8584,
  "longitude": 2.2945,
  "language": "en"
}
```

### Routing

**POST** `/directions`
```json
{
  "origin": "Eiffel Tower, Paris",
  "destination": "Louvre Museum, Paris",
  "mode": "walking",
  "alternatives": false,
  "language": "en"
}
```

**POST** `/distance-matrix`
```json
{
  "origins": ["Eiffel Tower", "Arc de Triomphe"],
  "destinations": ["Louvre", "Notre Dame"],
  "mode": "driving",
  "language": "en"
}
```

### Places

**POST** `/places/details`
```json
{
  "place_id": "ChIJLU7jZClu5kcR4PcOOO6p3I0",
  "fields": ["name", "photos", "rating", "reviews"],
  "language": "en"
}
```

**POST** `/places/nearby`
```json
{
  "latitude": 48.8584,
  "longitude": 2.2945,
  "radius": 1500,
  "type": "restaurant",
  "keyword": "french cuisine"
}
```

### Environmental

**POST** `/air-quality`
```json
{
  "latitude": 48.8584,
  "longitude": 2.2945
}
```

**POST** `/street-view/metadata`
```json
{
  "latitude": 48.8584,
  "longitude": 2.2945,
  "size": "600x400",
  "heading": 90
}
```

## LangChain Tools

5 tools automatically available to LLM when Extended Search (Brave Search) is enabled:

```python
# Example LLM queries that trigger tools:
"What's the address of the Eiffel Tower?" → geocode_address()
"How do I walk from A to B?" → get_directions(mode="walking")
"Find restaurants near coordinates" → search_nearby_places(type="restaurant")
"What's the air quality in Paris?" → get_air_quality()
"Show me street view of this location" → get_street_view()
```

## Configuration

**Environment Variables** (in `.env`):
```bash
GOOGLE_MAPS_API_KEY=your_api_key_here
REDIS_HOST=redis
REDIS_PORT=6379
CACHE_TTL=86400  # 24h default
```

**Enabled in LLM requests**:
Google Maps tools are automatically activated when Extended Search (Brave Search) is enabled.
Simply enable Extended Search in the chat UI - no additional configuration needed.

## Caching Strategy

| Endpoint | TTL | Reason |
|----------|-----|--------|
| Geocoding | 24h | Addresses rarely change |
| Places Details | 6h | Reviews/ratings update slowly |
| Directions | 1h | Traffic patterns change |
| Nearby Search | 1h | Business hours/availability varies |
| Air Quality | 1h | Environmental data changes hourly |

## Cost Optimization

**Without caching** (1000 requests/day):
- Geocoding: $5/1000 = $5/day = $150/month

**With caching** (90% cache hit rate):
- API calls: 100/day
- Cost: $0.50/day = $15/month
- **Savings: $135/month (90%)**

## Development

**Start service**:
```bash
docker-compose up -d google-maps
```

**View logs**:
```bash
docker logs google-maps --tail 50 -f
```

**Test endpoints**:
```bash
curl http://localhost:8005/
```

## Production Recommendations

1. **Monitor cache hit rate** in Redis
2. **Set TTL per use case** (static data = longer TTL)
3. **Enable API restrictions** in Google Cloud Console
4. **Set billing alerts** at $50, $100, $200
5. **Rate limit per user** if needed

## Next Steps (Future Enhancement)

- [ ] Weather API implementation
- [ ] Batch geocoding endpoint
- [ ] Place autocomplete/search
- [ ] Time Zone API
- [ ] Elevation API
- [ ] Per-user rate limiting
- [ ] Analytics dashboard

## Troubleshooting

**Service won't start**:
- Check `GOOGLE_MAPS_API_KEY` is set in `.env`
- Verify Redis is running: `docker ps | grep redis`

**API errors**:
- Check billing enabled in Google Cloud
- Verify API restrictions allow requests
- Check logs: `docker logs google-maps`

**Cache not working**:
- Verify Redis connection in startup logs
- Check Redis: `docker exec google-maps redis-cli ping`
