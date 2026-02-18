# AI-Assisted Application Configuration Tool - Implementation Documentation- Mustafa Emir Utku

## Overview

This document explains the design decisions, implementation details, and trade-offs made while building the AI-Assisted Application Configuration Tool. The system allows users to modify application configurations using natural language requests.

---

## Design Decisions

### 1. LLM Model Selection: llama3.2 (configurable)

**Why llama3.2?**
- **Local-machine friendly**: llama3.2 (3B parameter version) runs efficiently on consumer hardware without requiring a GPU
- **Good instruction following**: Excellent at following specific output format instructions, which is critical for generating valid JSON
- **Fast inference**: Quick response times compared to larger models
- **Sufficient capability**: Handles configuration understanding and JSON manipulation well

**Trade-offs:**
- Larger models (llama3.1:70b) might produce more accurate results but require significantly more resources
- Smaller models might fail more often on complex nested JSON structures

**Note:** The model is configurable via `LLM_MODEL` environment variable. Other models (e.g., `qwen3:4b`) can be used if they provide better performance or accuracy for the specific use case.

### 2. Framework Choice: Flask

**Why Flask?**
- **Simplicity**: Minimal boilerplate, easy to understand and maintain
- **Lightweight**: Small footprint, fast startup time
- **Python ecosystem**: Excellent integration with jsonschema and requests libraries
- **Production-ready with Gunicorn**: Easily deployable with a WSGI server

**Trade-offs:**
- FastAPI would provide automatic OpenAPI documentation and async support
- Flask's synchronous nature is sufficient for this use case since LLM calls are blocking anyway

### 3. Retry Mechanism: Max 3 Retries

**Why 3 retries?**
- LLMs can occasionally produce malformed JSON or values that don't pass schema validation
- 3 retries provides a good balance between reliability and response time
- Each retry gives the LLM another chance to produce valid output

**Implementation:**
```
User Input → LLM generates JSON → Validate against schema
                                         ↓
                              Pass → Return response
                                         ↓
                              Fail → Retry (max 3 times)
```

### 4. Ollama Deployment: Host vs Container

**Why host Ollama (recommended)?**
- **Performance**: Host Ollama can use GPU/Metal acceleration (e.g., on Mac), providing 10x faster inference compared to CPU-only Docker container
- **Resource efficiency**: Host Ollama shares resources better with the host OS
- **Easier debugging**: Direct access to Ollama logs and metrics on the host

**Trade-offs:**
- Docker container Ollama is more isolated but slower (CPU-only, no GPU access)
- Host Ollama requires manual setup and management outside Docker Compose
- For production, containerized Ollama might be preferred for consistency, but requires GPU passthrough configuration

**Implementation:** The bot service connects to Ollama via `OLLAMA_URL` environment variable. Default is `http://host.docker.internal:11434` (host Ollama), but can be changed to `http://ollama:11434` if using containerized Ollama.

### 5. Token Limit Configuration: OLLAMA_NUM_PREDICT

**Why 4096 tokens?**
- Large configuration JSON files (e.g., tournament schema ~68KB) require sufficient token budget for complete responses
- Lower values (e.g., 1024) often truncate responses, causing JSON parse errors and validation failures
- 4096 provides headroom for complex nested configurations while maintaining reasonable response times

**Trade-offs:**
- Higher token limits increase response time and resource usage
- Lower limits can cause truncation but may speed up inference for simple requests
- Configurable via `OLLAMA_NUM_PREDICT` environment variable (default: 4096)

### 6. Structured Logging and Request Tracking

**Why structured logging?**
- **Correlation**: Each request gets a unique request ID (`req-{uuid}`) for tracing across services
- **Debugging**: Structured format `[request_id] [app_name] [action] message key=value` makes log analysis easier
- **Monitoring**: Enables filtering and aggregation of logs by request, application, or action

**Implementation:**
- Request ID generated at the start of each `/message` request
- All log events include the request ID for correlation
- Logs follow format: `[request_id] [app_name] [action] message key=value`

### 7. Input Validation

**Why MAX_INPUT_LENGTH = 2000?**
- Prevents extremely long inputs that could cause prompt size issues or abuse
- Balances usability with system constraints
- Returns clear error message if exceeded

**Implementation:**
- Input length checked before processing
- Returns 400 Bad Request if input exceeds limit

---

## System Architecture

### Service Overview

| Service | Port | Responsibility |
|---------|------|----------------|
| Schema Service | 5001 | Serves JSON Schema definitions |
| Values Service | 5002 | Serves current configuration values |
| Bot Service | 5003 | Processes natural language requests |
| Ollama | 11434 | Local LLM inference |

### Service Communication

```
                    ┌─────────────────┐
                    │   User/Client   │
                    └────────┬────────┘
                             │ POST /message
                             ▼
                    ┌─────────────────┐
                    │   Bot Service   │ (port 5003 - external)
                    │   (Flask/Gunicorn) │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Schema Service│   │ Values Service│   │    Ollama     │
│  (port 5001)  │   │  (port 5002)  │   │ (port 11434)  │
└───────────────┘   └───────────────┘   └───────────────┘
        │                    │
        ▼                    ▼
   /data/schemas        /data/values
   (read-only)          (read-only)
```

### Network Topology

- All services communicate through an internal Docker network (`app-network`)
- Only port 5003 (Bot Service) is exposed to the external world
- Schema and Values services are internal only (ports 5001 and 5002 are not exposed by default)
- Ollama runs on the host machine (not in Docker) and is accessed via `host.docker.internal:11434`

---

## End-to-End Request Flow

### Example Request
```bash
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set tournament service memory to 1024mb"}'
```

### Step-by-Step Flow

1. **User sends request** to Bot Service `/message` endpoint
   - Input: `{"input": "set tournament service memory to 1024mb"}`

2. **Bot Service identifies application** using LLM
   - Sends prompt to Ollama asking to identify which app (chat/tournament/matchmaking)
   - LLM responds with: `tournament`

3. **Bot Service fetches schema**
   - `GET http://schema-server:5001/tournament`
   - Receives JSON Schema for tournament application

4. **Bot Service fetches current values**
   - `GET http://values-server:5002/tournament`
   - Receives current configuration JSON

5. **Bot Service generates updated values** using LLM
   - Sends prompt with:
     - User request
     - Current values
     - JSON Schema
   - LLM generates modified JSON with `memory.limitMiB: 1024`

6. **Bot Service validates output**
   - Validates LLM output against JSON Schema
   - If invalid, retries up to 3 times

7. **Bot Service returns response**
   - Returns the updated configuration JSON to the user

---

## Security Considerations

### Container Security
- All services run as non-root user (`appuser`)
- Data volumes are mounted as read-only where appropriate
- Only necessary ports are exposed (5003 for external access)

### Network Security
- Internal services (schema-server, values-server, ollama) are not exposed externally
- Services communicate through isolated Docker network

### Input Validation
- User input length is limited to 2000 characters (`MAX_INPUT_LENGTH`)
- User input is sanitized through LLM processing
- Output is validated against strict JSON Schema before returning
- Invalid JSON responses from LLM trigger retries (up to 3 attempts)

### Observability
- Structured logging with request ID correlation for all requests
- Health check endpoints (`/health`) for all services
- Service health monitoring (checks Ollama, Schema, and Values services availability)
- Error messages include context (request ID, service name, error type)

---

## Configuration Options

### Environment Variables

| Service | Variable | Default | Description |
|---------|----------|---------|-------------|
| schema-server | SCHEMA_DIR | /data/schemas | Schema files directory |
| values-server | VALUES_DIR | /data/values | Values files directory |
| bot-server | OLLAMA_URL | http://host.docker.internal:11434 | Ollama API endpoint (host Ollama recommended) |
| bot-server | SCHEMA_SERVICE_URL | http://schema-server:5001 | Schema service endpoint |
| bot-server | VALUES_SERVICE_URL | http://values-server:5002 | Values service endpoint |
| bot-server | LLM_MODEL | llama3.2 | Ollama model to use (configurable) |
| bot-server | OLLAMA_NUM_PREDICT | 4096 | Maximum tokens for LLM response (prevents truncation) |

---

## How to Run

### Prerequisites
- Docker and Docker Compose installed
- Ollama installed and running on the host machine (not in Docker)
- Ollama model downloaded (e.g., `ollama pull llama3.2` or `ollama pull qwen3:4b`)

### Start Services
```bash
docker compose up --build -d
```

**Note:** The Ollama service is commented out in `docker-compose.yml` by default. The bot connects to Ollama running on the host via `host.docker.internal:11434`. If you prefer containerized Ollama, uncomment the Ollama service in `docker-compose.yml` and change `OLLAMA_URL` to `http://ollama:11434`.

### Pull LLM Model (if using host Ollama)
```bash
ollama pull llama3.2

```

### Test the System
```bash
# Test Bot Service (main endpoint)
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set tournament service memory to 1024mb"}'

# Test with response time measurement
curl -s -w "\nTotal time: %{time_total}s\n" -o /dev/stdout \
  -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set tournament service memory to 1024mb"}'

# Health check
curl http://localhost:5003/health
```

**Note:** Schema and Values services are not exposed externally (ports 5001 and 5002 are internal only). They can be tested from within the Docker network or by temporarily exposing ports in `docker-compose.yml`.

### Test Results

- `curl http://localhost:5003/health` → `{"status":"healthy","dependencies":{"ollama":"healthy","schema_service":"healthy","values_service":"healthy"}}`
- `curl -X POST http://localhost:5003/message -H "Content-Type: application/json" -d '{"input": "set tournament service memory to 1024mb"}'` → Returns updated tournament config with `memory.limitMiB` and `memory.requestMiB` set to 1024; total time ~48.5s (host Ollama, macOS).
- Tests were run locally (macOS) after `docker compose up`.

### View Logs
```bash
# All services
docker compose logs -f

# Only bot-server (recommended for debugging)
docker compose logs -f bot-server

# Last 50 lines + follow
docker compose logs -f --tail=50 bot-server
```

Logs include structured format with request IDs: `[request_id] [app_name] [action] message key=value`

---

## Assumptions Made

1. **Application naming**: Users refer to applications by their common names (chat, tournament, matchmaking)
2. **Memory units**: When users say "1024mb", we interpret this as MiB (mebibytes) for the `limitMiB` field
3. **CPU units**: CPU values in the schema are in milliCPU (1000 = 1 core)
4. **Stateless operation**: The system does not persist changes; it returns the modified JSON for the user to apply
5. **Single modification per request**: Each request modifies one aspect of the configuration

---

## Potential Improvements

1. **Caching**: Add Redis caching for frequently accessed schemas/values
2. **Streaming**: Implement streaming responses for real-time LLM output
3. **Persistence**: Add option to save modified configurations
4. **Multi-language support**: Enhance prompts for better Turkish language support
5. **Batch operations**: Support multiple modifications in a single request
6. **Audit logging**: Track all configuration changes for compliance
7. **Prompt optimization**: Reduce prompt size by sending only relevant schema sections instead of full schema (~68KB) to improve LLM response time
8. **Metrics and monitoring**: Add Prometheus metrics and Grafana dashboards for request rates, response times, and error rates
9. **Rate limiting**: Implement rate limiting to prevent abuse
10. **Configuration validation**: Pre-validate user requests before sending to LLM to catch obvious errors early

---
