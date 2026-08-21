# User Preferences Microservice

A standalone FastAPI microservice for managing user preferences across applications.

## Features

- ✅ **Standalone service** - Can be used with any application
- ✅ **JWT Authentication** - Secures user preferences with JWT tokens
- ✅ **JSONB Storage** - Flexible preference values (strings, numbers, objects, arrays)
- ✅ **Category Organization** - Group preferences by category
- ✅ **Auto-documentation** - Swagger UI and ReDoc included
- ✅ **Type-safe** - Pydantic schemas for validation
- ✅ **Database migrations** - SQL migration scripts included

## Quick Start

### Using Docker Compose

```bash
# Build and start the service
docker-compose up user-preferences

# Access the API documentation
open http://localhost:8002/docs
```

### Local Development

```bash
cd user-preferences-service

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/sterna_dev"
export JWT_SECRET_KEY="your-secret-key"

# Run the service
uvicorn app.main:app --reload --port 8002
```

## API Endpoints

All endpoints require a valid JWT Bearer token in the Authorization header:
```
Authorization: Bearer <your_access_token>
```

### Get All Preferences
```http
GET /api/v1/preferences
GET /api/v1/preferences?category=ui
```

### Get Specific Preference
```http
GET /api/v1/preferences/ui.theme
```

### Update/Create Preference
```http
PUT /api/v1/preferences/ui.theme
Content-Type: application/json

{
  "preference_value": "dark",
  "category": "ui"
}
```

### Bulk Update
```http
PUT /api/v1/preferences
Content-Type: application/json

{
  "preferences": {
    "ui.theme": "dark",
    "ui.sidebar_collapsed": false,
    "models.favorites": ["gpt-4", "claude-3"]
  }
}
```

### Delete Preference
```http
DELETE /api/v1/preferences/ui.theme
```

## Database Migration

Run the SQL migration to create the `user_preferences` table:

```bash
psql -U postgres -d sterna_dev -f migrations/001_create_user_preferences_table.sql
```

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `JWT_SECRET_KEY` | Secret key for JWT validation | Required |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:5173` |
| `DEBUG` | Enable debug mode | `False` |

## Examples

### Python Client

```python
import requests

API_URL = "http://localhost:8002"
TOKEN = "your_jwt_token"
headers = {"Authorization": f"Bearer {TOKEN}"}

# Get all preferences
response = requests.get(f"{API_URL}/api/v1/preferences", headers=headers)
print(response.json())

# Update a preference
requests.put(
    f"{API_URL}/api/v1/preferences/ui.theme",
    headers=headers,
    json={"preference_value": "dark", "category": "ui"}
)
```

### JavaScript/TypeScript Client

```typescript
const API_URL = "http://localhost:8002";
const token = localStorage.getItem("access_token");

// Get all preferences
const response = await fetch(`${API_URL}/api/v1/preferences`, {
  headers: {
    "Authorization": `Bearer ${token}`
  }
});
const {preferences} = await response.json();

// Update preference
await fetch(`${API_URL}/api/v1/preferences/ui.theme`, {
  method: "PUT",
  headers: {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    preference_value: "dark",
    category: "ui"
  })
});
```

## Preference Key Conventions

Use dot notation for preference keys:

- `ui.theme` - UI theme (light/dark)
- `ui.sidebar_collapsed` - Sidebar state
- `ui.navigation_order` - Custom navigation order
- `models.favorites` - Favorite models list
- `models.recent` - Recently used models (global app usage)
- `models.recent_chat` - Recently used models in /chats page
- `models.active_chat_group` - Last opened conversation in /chats page
- `onboarding.completed` - Onboarding status
- `onboarding.current_step` - Current onboarding step

## Health Check

```http
GET /health
```

Returns:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-10-06T12:00:00Z"
}
```

## Development

### Running Tests

```bash
pytest
```

### Code Style

```bash
black app/
isort app/
flake8 app/
```

## Architecture

```
┌─────────────────┐
│   Frontend      │
│  (React/Vue)    │
└────────┬────────┘
         │ JWT Token
         ↓
┌─────────────────┐
│  User Prefs API │  ← FastAPI
│  (Port 8002)    │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   PostgreSQL    │  ← user_preferences table
└─────────────────┘
```

## License

MIT License - See LICENSE file for details

## Support

For issues or questions, please open an issue on GitHub.
