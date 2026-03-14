# AURA Backend API Endpoints

> Auto-generated: January 31, 2026

## Overview

The AURA backend uses a versioned API structure with backward compatibility for the Android app.

- **Versioned API Prefix:** `/api/v1`
- **Legacy Prefix:** Root level (`/device/*`, `/tasks/*`, etc.)

---

## Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Legacy health check (redirects to versioned) |
| GET | `/api/v1/health` | Comprehensive health check with service status |
| POST | `/api/v1/test/hitl` | Test HITL dialog (confirmation, choice, text input) |

---

## Device Management

### Versioned Endpoints (`/api/v1/device/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/device/register` | Register device with API key auth |
| GET | `/api/v1/device/status` | Get device connection status with troubleshooting hints |
| GET | `/api/v1/device/ui-elements` | Get current UI elements via UITreeService |
| POST | `/api/v1/device/request-screen-capture` | Request screen capture permission dialog |

### Legacy Endpoints (`/device/*`) - For Android App

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/device/register` | Register Android device |
| GET | `/device/status` | Get device connection status |
| POST | `/device/ui-data` | Upload UI hierarchy and screenshot |
| POST | `/device/execute-gesture` | Execute gesture (tap, swipe, etc.) |
| GET | `/device/ui-snapshot` | Get current UI snapshot |
| POST | `/device/request-ui` | Request fresh UI capture |
| POST | `/device/disconnect` | Disconnect device |
| GET | `/device/commands/pending` | Get pending commands (polling) |
| POST | `/device/commands/{command_id}/result` | Report command result |
| POST | `/device/commands/queue` | Queue command for execution |
| GET | `/device/apps/{device_name}` | Get installed apps inventory |
| POST | `/device/gesture-ack` | Receive gesture acknowledgment |
| POST | `/device/screen-capture-permission` | Receive permission result |

---

## Task Execution

### Versioned Endpoints (`/api/v1/tasks/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tasks/execute` | Execute voice command task |
| POST | `/api/v1/tasks/execute-file` | Execute task from uploaded audio file |

### Legacy Endpoints (`/tasks/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tasks/execute` | Execute voice command task |
| POST | `/tasks/execute-file` | Execute from audio file |
| GET | `/tasks/token-stats` | Get token usage statistics |
| POST | `/tasks/token-stats/reset` | Reset token tracking |

---

## Accessibility Service

### Versioned Endpoints (`/api/v1/accessibility/*`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/accessibility/connect` | Connect accessibility service |
| GET | `/api/v1/accessibility/current-ui` | Get current UI state |
| GET | `/api/v1/accessibility/device-info` | Get connected device info |
| POST | `/api/v1/accessibility/execute-gesture` | Execute gesture action |
| POST | `/api/v1/accessibility/find-element` | Find UI element by criteria |
| GET | `/api/v1/accessibility/screenshot` | Get current screenshot |
| POST | `/api/v1/accessibility/ui-data` | Upload UI data |

### Legacy Endpoints (`/accessibility/*`)

Same endpoints available at root for backward compatibility.

---

## Workflow Visualization

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/workflow/sessions` | List recent workflow sessions |
| GET | `/api/v1/workflow/{session_id}` | Get workflow details |
| DELETE | `/api/v1/workflow/{session_id}` | Delete a session |
| DELETE | `/api/v1/workflow/sessions/all` | Clear all sessions |
| GET | `/api/v1/workflow/viewer/ui` | Workflow viewer HTML page |
| GET | `/api/v1/workflow/viewer/flow` | Flow-based viewer |
| GET | `/api/v1/workflow/viewer/visual` | Visual flow with connected agents |

---

## Graph & Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/graph/info` | Get LangGraph configuration info |
| GET | `/api/v1/config` | Get current configuration |

---

## WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ws` | Main device WebSocket (UI data, gestures, HITL) |
| `/ws/audio-stream` | Real-time audio streaming for STT |
| `/ws/audio-stream-final` | Final transcript and task execution |

---

## Request/Response Examples

### Execute Text Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks/execute \
  -H "Content-Type: application/json" \
  -d '{
    "text_input": "open settings",
    "input_type": "text"
  }'
```

### Test HITL Dialog

```bash
curl -X POST http://localhost:8000/api/v1/test/hitl \
  -H "Content-Type: application/json" \
  -d '{
    "question_type": "confirmation",
    "title": "Confirm Action",
    "message": "Do you want to proceed?",
    "timeout": 30
  }'
```

### Get Device Status

```bash
curl http://localhost:8000/api/v1/device/status
```

### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

---

## Authentication

Device registration requires API key in header:

```
X-API-Key: your-device-api-key
```

Configure in `.env`:
```
DEVICE_API_KEY=your-secure-key
```

---

## Error Responses

All endpoints return standard error format:

```json
{
  "detail": "Error message here"
}
```

HTTP Status Codes:
- `200` - Success
- `400` - Bad Request
- `401` - Unauthorized
- `404` - Not Found
- `429` - Rate Limited
- `500` - Internal Server Error
- `503` - Service Unavailable

---

## Rate Limits

| Endpoint Pattern | Limit |
|------------------|-------|
| `/health` | 60/minute |
| `/device/status` | 60/minute |
| `/tasks/execute` | 30/minute |
| `/` (root) | 30/minute |
