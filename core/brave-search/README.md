# Brave Search Service

Dedicated Docker service providing advanced search capabilities via the Brave Search API.

## Features

This service exposes 5 different search types:

### 1. **Web Search** (`/search/web`)
Full web search with enriched snippets
- Results with title, URL, description
- Freshness filters (day, week, month, year)
- Configurable safe search
- Pagination

### 2. **Image Search** (`/search/images`)
Image search
- High-resolution image URLs
- Thumbnails
- Metadata (dimensions, source)
- Up to 150 results per query

### 3. **Local Search** (`/search/local`)
Business and place search
- Business info (name, address, phone)
- Ratings and reviews
- AI-generated descriptions
- Geolocation

### 4. **Video Search** (`/search/videos`)
Video search
- Titles and descriptions
- Duration and view counts
- Thumbnails
- Video URLs

### 5. **News Search** (`/search/news`)
News search
- Recent articles
- Freshness control
- Publication dates
- News sources

## Configuration

### Brave API Key

To use this service, you need to obtain a Brave Search API key:

1. Create an account at [Brave Search API](https://brave.com/search/api/)
2. Generate an API key
3. Add the key to your `.env` file:

```bash
BRAVE_API_KEY=your_api_key_here
```

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `BRAVE_API_KEY` | Brave Search API key | Yes | - |

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   LangChain     │         │  Brave Search    │         │   Brave Search  │
│   Agent         │────────>│    Service       │────────>│   API           │
│  (via tools)    │         │  (FastAPI)       │         │  (External)     │
└─────────────────┘         └──────────────────┘         └─────────────────┘
```

### Data flow

1. **LangChain agent** calls a Brave Search tool (e.g. `brave_web_search`)
2. **LangChain tool** sends an HTTP request to the Brave Search service
3. **FastAPI service** transforms the request and calls the Brave API
4. **Brave API** returns the results
5. **Service** formats and returns the results to the tool
6. **Tool** returns the results to the agent as JSON

## Usage

### Via LangChain Tools

The tools are automatically available when `enable_brave_search=True`:

```python
from llm.langchain_agent import LangChainStreamingAgent

agent = LangChainStreamingAgent(
    model="anthropic/claude-3.5-sonnet",
    api_key="...",
    enable_brave_search=True  # Enables the Brave Search tools
)
```

### Available tools

1. **`brave_web_search`** - General web search
2. **`brave_image_search`** - Image search
3. **`brave_local_search`** - Place/business search
4. **`brave_video_search`** - Video search
5. **`brave_news_search`** - News search

### Direct API call example

```bash
# Web search
curl -X POST http://localhost:8004/search/web \
  -H "Content-Type: application/json" \
  -d '{
    "query": "latest AI developments",
    "count": 10,
    "freshness": "pw"
  }'

# Image search
curl -X POST http://localhost:8004/search/images \
  -H "Content-Type: application/json" \
  -d '{
    "query": "sunset mountains",
    "count": 20
  }'

# Local search
curl -X POST http://localhost:8004/search/local \
  -H "Content-Type: application/json" \
  -d '{
    "query": "restaurants Paris",
    "count": 5
  }'
```

## Endpoints

### Health Check
```
GET /
```

Returns the service status and whether the API key is configured.

### Web Search
```
POST /search/web
```

**Body:**
```json
{
  "query": "search query",
  "count": 10,
  "safesearch": "moderate",
  "freshness": "pw"
}
```

### Image Search
```
POST /search/images
```

**Body:**
```json
{
  "query": "search query",
  "count": 10,
  "safesearch": "moderate"
}
```

### Local Search
```
POST /search/local
```

**Body:**
```json
{
  "query": "business name",
  "count": 5
}
```

### Video Search
```
POST /search/videos
```

**Body:**
```json
{
  "query": "search query",
  "count": 10,
  "safesearch": "moderate"
}
```

### News Search
```
POST /search/news
```

**Body:**
```json
{
  "query": "search query",
  "count": 10,
  "freshness": "pd"
}
```

## Development

### Starting the service

```bash
# Via Docker Compose
docker-compose up brave-search

# Locally (for development)
cd brave-search
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8004 --reload
```

### Logs

Logs include:
- Requests received
- Calls to the Brave API
- Number of results returned
- API errors

Structured JSON format for easier debugging.

## Security

- **API key**: Stored as an environment variable, never in code
- **Rate limiting**: Handled by the Brave Search API
- **CORS**: Configured to accept requests from the frontend
- **Timeouts**: 30 seconds max per request
- **Validation**: All parameters validated with Pydantic

## Resource limits

The service is configured with the following Docker limits:
- **CPU**: 0.5 core max
- **Memory**: 512MB max

## Troubleshooting

### Service doesn't start
```bash
# Check the logs
docker logs brave-search

# Check that port 8004 is available
lsof -i :8004
```

### "API key not configured" error
```bash
# Check that BRAVE_API_KEY is defined
docker-compose config | grep BRAVE_API_KEY

# Add it to the .env file
echo "BRAVE_API_KEY=your_key" >> .env

# Restart the service
docker-compose restart brave-search
```

### No results
- Check that the API key is valid
- Check the Brave API quotas
- Try a different query
- Check the service logs

## External documentation

- [Brave Search API Docs](https://api.search.brave.com/app/documentation)
- [Brave Search Pricing](https://brave.com/search/api/)
- [Brave MCP Server (GitHub)](https://github.com/brave/brave-search-mcp-server)

## Support

For issues related to:
- **Service**: Check the Docker logs
- **Brave API**: Consult the Brave documentation
- **LangChain Tools**: Check `llm/brave_search_tools.py`
