# Runway API Documentation

> Last updated: January 2026

## Overview

The Runway API provides access to multiple video generation models. This document covers all available models, their capabilities, and implementation details.

## API Configuration

| Setting | Value |
|---------|-------|
| **Base URL** | `https://api.dev.runwayml.com/v1` |
| **API Version** | `2024-11-06` |
| **Auth Header** | `Authorization: Bearer <API_KEY>` |
| **Version Header** | `X-Runway-Version: 2024-11-06` |
| **Content-Type** | `application/json` |

### Authentication

```bash
# Required headers for all requests
Authorization: Bearer <YOUR_API_KEY>
X-Runway-Version: 2024-11-06
Content-Type: application/json
```

API keys are generated at [dev.runwayml.com](https://dev.runwayml.com/). Minimum $10 deposit required before API access is enabled.

---

## Available Models

### Text-to-Video Models (No Image Required)

These models support pure text-to-video generation:

| Model | Credits/sec | With Audio | Duration | Best For |
|-------|-------------|------------|----------|----------|
| `veo3.1` | 20 | 40 | 4, 6, 8 sec | High quality, lip-sync audio |
| `veo3.1_fast` | 15 | - | 4, 6, 8 sec | Rapid prototyping |
| `veo3` | 20 | 40 | 4, 6, 8 sec | General purpose |

### Image-to-Video Models (Image Required)

These models require an input image:

| Model | Credits/sec | Duration | Best For |
|-------|-------------|----------|----------|
| `gen4_turbo` | 5 | 5, 10 sec | Fast iteration, cost-effective |
| `gen4_aleph` | 15 | max 5 sec | Video-to-video transformation |

### Other Models

| Model | Credits/sec | Purpose |
|-------|-------------|---------|
| `upscale_v1` | 2 | 4X video upscaling |
| `act_two` | 5 | Character performance |

---

## Model Details

### Veo 3.1 (Recommended for Text-to-Video)

**Endpoint:** `POST /v1/text_to_video`

**Capabilities:**
- Pure text-to-video (no image required)
- Native audio generation with lip-sync
- Up to 8 seconds per generation
- 720p or 1080p output

**Request Example:**
```json
{
  "model": "veo3.1",
  "promptText": "A serene lake at sunset with mountains in the background, cinematic drone shot",
  "ratio": "1280:720",
  "duration": 8,
  "generateAudio": true
}
```

**Pricing:**
- Without audio: 20 credits/sec ($0.20/sec)
- With audio: 40 credits/sec ($0.40/sec)
- 8-second video with audio: 320 credits ($3.20)

### Veo 3.1 Fast

Same capabilities as Veo 3.1 but optimized for speed. Use for rapid prototyping.

**Pricing:** 15 credits/sec ($0.15/sec)

### Gen4 Turbo (Image-to-Video)

**Endpoint:** `POST /v1/image_to_video`

**Capabilities:**
- Requires input image
- Optional text prompt for guidance
- 5 or 10 second output
- Most cost-effective option

**Request Example:**
```json
{
  "model": "gen4_turbo",
  "promptImage": "https://example.com/image.jpg",
  "promptText": "Camera slowly zooms in as clouds move across the sky",
  "ratio": "1280:720",
  "duration": 10
}
```

**Pricing:** 5 credits/sec ($0.05/sec)
- 10-second video: 50 credits ($0.50)

---

## Supported Resolutions

| Ratio | Resolution | Type |
|-------|------------|------|
| `1280:720` | 1280x720 | Landscape HD |
| `720:1280` | 720x1280 | Portrait HD |
| `1920:1080` | 1920x1080 | Landscape FHD |
| `1080:1920` | 1080x1920 | Portrait FHD |
| `960:960` | 960x960 | Square |
| `1584:672` | 1584x672 | Cinematic wide |
| `1104:832` | 1104x832 | 4:3 landscape |
| `832:1104` | 832x1104 | 3:4 portrait |

---

## API Endpoints

### Create Task

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/text_to_video` | Text-to-video generation |
| `POST /v1/image_to_video` | Image-to-video generation |
| `POST /v1/video_to_video` | Video transformation |
| `POST /v1/video_upscale` | 4X video upscaling |

### Task Management

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/tasks/{id}` | Get task status |
| `POST /v1/tasks/{id}/cancel` | Cancel running task |
| `DELETE /v1/tasks/{id}` | Delete completed task |

---

## Task Lifecycle

### Status Values

| Status | Description |
|--------|-------------|
| `QUEUED` | Waiting to be processed |
| `RUNNING` | Currently processing |
| `THROTTLED` | Queued due to concurrency limits (treat as PENDING) |
| `SUCCEEDED` | Completed successfully |
| `FAILED` | Task failed |
| `CANCELED` | Task was canceled |

### Polling Strategy

- Poll every **5+ seconds** with jitter
- Use exponential backoff for failures
- Default timeout: 10 minutes
- Output URLs expire in **24-48 hours**

### Example Response (Success)

```json
{
  "id": "task-abc123",
  "status": "SUCCEEDED",
  "createdAt": "2026-01-19T12:00:00Z",
  "output": [
    {
      "type": "video",
      "url": "https://cdn.runwayml.com/..."
    }
  ]
}
```

---

## Input Requirements

### Size Limits

| Input Type | URL | Data URI | Ephemeral Upload |
|------------|-----|----------|------------------|
| Image | 16 MB | 5 MB | 200 MB |
| Video | 32 MB | 16 MB | 200 MB |
| Audio | 32 MB | 16 MB | 200 MB |

### URL Requirements

- Must use HTTPS (not HTTP)
- Must use domain name (not IP address)
- Server must provide `Content-Type` and `Content-Length` headers
- Must support HTTP HEAD requests
- Redirects are NOT followed
- Download timeout: 10 seconds

### Supported Formats

- **Images:** JPEG, PNG, WebP (NOT GIF)
- **Videos:** MP4, QuickTime, Matroska, WebM, 3GPP
- **Audio:** MP3, WAV, FLAC, M4A, AAC

---

## Rate Limits & Tiers

| Tier | Concurrent Tasks | Daily Generations | Monthly Spend |
|------|------------------|-------------------|---------------|
| Tier 1 | 1 | 50 | $100 |
| Tier 2 | 2 | 500 | $500 |
| Tier 3 | 5 | 2,500 | $5,000 |
| Tier 4 | 10 | 10,000 | $20,000 |
| Tier 5 | 20 | 25,000 | $100,000 |

- No requests-per-minute limit (queue-based system)
- Daily limits use **rolling 24-hour window**
- Excess requests automatically queued

---

## Error Handling

### HTTP Status Codes

| Status | Meaning | SDK Action |
|--------|---------|------------|
| 400 | Bad Request | Check parameters |
| 408 | Timeout | Auto-retry |
| 409 | Conflict | Auto-retry |
| 429 | Rate Limited | Auto-retry |
| 503 | Service Unavailable | Auto-retry |
| 5xx | Server Error | Auto-retry |

### Common 400 Errors

- URL uses `http://` instead of `https://`
- URL uses IP address instead of domain name
- Server doesn't return `Content-Length` header
- Asset exceeds 8000px dimension limit
- Unsupported format or `application/octet-stream` content type
- Timeout fetching asset (>10 seconds)

---

## Pricing Summary

### Cost per Second (1 credit = $0.01)

| Model | Credits/sec | USD/sec |
|-------|-------------|---------|
| `gen4_turbo` | 5 | $0.05 |
| `veo3.1_fast` | 15 | $0.15 |
| `gen4_aleph` | 15 | $0.15 |
| `veo3.1` (no audio) | 20 | $0.20 |
| `veo3` / `veo3.1` (with audio) | 40 | $0.40 |

### Example Costs

| Scenario | Cost |
|----------|------|
| 10s gen4_turbo video | $0.50 |
| 8s veo3.1 without audio | $1.60 |
| 8s veo3.1 with audio | $3.20 |
| 5s gen4_aleph transformation | $0.75 |

---

## Implementation Recommendations

### For Text-to-Video (No Image Input)

**Use `veo3.1` or `veo3.1_fast`**

```python
# Recommended for text-to-video
payload = {
    "model": "veo3.1",  # or "veo3.1_fast" for speed
    "promptText": "Your detailed video description",
    "ratio": "1280:720",
    "duration": 8,
    "generateAudio": False  # Set True for audio (2x cost)
}
response = client.post("/v1/text_to_video", json=payload)
```

### For Image-to-Video

**Use `gen4_turbo`** (most cost-effective)

```python
# Recommended for image-to-video
payload = {
    "model": "gen4_turbo",
    "promptImage": "https://example.com/image.jpg",
    "promptText": "Optional motion description",
    "ratio": "1280:720",
    "duration": 10
}
response = client.post("/v1/image_to_video", json=payload)
```

---

## Official Resources

- [API Documentation](https://docs.dev.runwayml.com/)
- [API Reference](https://docs.dev.runwayml.com/api/)
- [Developer Portal](https://dev.runwayml.com/)
- [Available Models](https://docs.dev.runwayml.com/guides/models/)
- [Pricing Guide](https://docs.dev.runwayml.com/guides/pricing/)
- [Troubleshooting](https://docs.dev.runwayml.com/errors/troubleshooting/)

---

## Changelog

### January 2026
- Initial documentation
- Veo 3.1 models support text-to-video without image input
- Gen4 models require image input
