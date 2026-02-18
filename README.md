# AI-Assisted Application Configuration Tool

This repository contains my implementation of a **local, AI-driven configuration management system** that allows users to modify application configuration values using **natural language**.

It was originally built as an internship project and is now published publicly to showcase my experience with **Python microservices**, **Docker**, **local LLMs (Ollama)**, and **schema‑driven configuration management**.

Instead of manually editing JSON files, users can send plain-English requests such as:

- “set tournament service memory to 1024mb”
- “set GAME_NAME env to toyblast for matchmaking service”
- “lower cpu limit of chat service to %80”

The system understands the request, determines **which application is being referenced**, validates changes against the **application’s JSON Schema**, updates the **current values JSON**, and returns the modified configuration.

---

## Skills & Technologies Demonstrated

- **Backend & APIs**
  - Python + Flask services (`schema-server`, `values-server`, `bot-server`)
  - Clear separation of responsibilities between microservices
- **LLM / AI Integration**
  - Running a **local** LLM via **Ollama** (no cloud LLMs)
  - Prompt design for: app identification → config update generation
  - Handling malformed LLM output with retries and strict JSON Schema validation
- **Configuration & JSON Schema**
  - Designing and using JSON Schemas to validate configuration
  - Safely updating nested JSON while preserving unrelated fields
- **DevOps & Containerization**
  - Dockerizing each service with dedicated `Dockerfile`
  - Orchestrating services via `docker-compose.yml`
  - Using an internal Docker network for service‑to‑service communication
- **Reliability & Observability**
  - Structured, traceable logging with per‑request IDs
  - Health checks for services and dependencies (Ollama, schema, values)
  - Input validation and safe error handling

These pieces together demonstrate my ability to design, implement and operate a small but realistic **AI‑assisted backend system** end‑to‑end.

---

## Quick Start

### Prerequisites

- **Docker** and **Docker Compose**
- **Ollama** running on your machine
- An LLM model pulled in Ollama (for example: `ollama pull llama3.2`)

### Run the system

```bash
docker compose up --build -d
```

This will start:

- `schema-server` (JSON Schemas)
- `values-server` (current configuration values)
- `bot-server` (public API you call)

By default, the Bot Service expects Ollama on `http://host.docker.internal:11434`. You can change this via the `OLLAMA_URL` environment variable.

### Try an example request

```bash
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set tournament service memory to 1024mb"}'
```

The response is the updated configuration JSON for the `tournament` application.

---

## High-Level Architecture

The system is composed of **three independent services**, each with a single responsibility:

### 1. Schema Service
- Serves **JSON Schemas** for applications
- Schemas define the **allowed structure, fields, and constraints**
- Each application is identified by a `app_name`

### 2. Values Service
- Serves the **current configuration values** for applications
- Values are stored separately from schemas
- Uses the same `app_name` to link values to schemas

### 3. Bot Service
- Accepts **natural language user input**
- Uses a **local LLM (via Ollama)** to:
  - Identify which application the user wants to modify
  - Understand the intended change
  - Apply the change **safely and structurally** to the values JSON
- Returns the **updated values JSON** to the caller

---

## Request Flow

1. **User sends a message** to the Bot Service:
   ```json
   { "input": "set tournament service memory to 1024mb" }
   ```

2. **Bot Service sends the user input to the AI model**
   - Expects **only the application name** (or application identifier) as output
   - No schema or values are provided at this stage

3. **Bot Service fetches application data**:
   - JSON Schema from the **Schema Service**
   - Current values JSON from the **Values Service**

4. **Bot Service sends a second request to the AI model**, providing:
   - The original user input
   - The application JSON Schema
   - The current values JSON
   - Expects the AI model to **respond only with the modified values JSON**

5. **AI model produces**:
   - A modified values JSON that:
     - Strictly follows the provided schema
     - Preserves all unrelated fields
     - Applies only the requested changes

6. **Bot Service returns**:
   - The updated values JSON as the response

---

## Services

### 1. Schema Service

* Create a schema service that provides a JSON Schema for a given application.

  - **request:**
    ```
        GET /{app_name}
    ```

  - **responses:**
    ```
        200 OK -> { json_schema }
        404 Not Found
        500 Internal Server Error
    ```

  - **arguments:**
    ```
        --schema-dir (default /data/schemas)
        --listen host:port (default "0.0.0.0:5001")
    ```

### 2. Values Service

* Create a values service that provides the current values for a given application.

  - **request:**
    ```
        GET /{app_name}
    ```

  - **responses:**
    ```
        200 OK -> { json_values }
        404 Not Found
        500 Internal Server Error
    ```

  - **arguments:**
    ```
        --schema-dir (default /data/values)
        --listen host:port (default "0.0.0.0:5002")
    ```

### 3. Bot Service

* Create a bot service that accepts a user message and returns an updated values JSON.
  - Receives the user message
  - Identifies which application the user wants to modify using an AI model
  - Retrieves the application schema from the schema service
  - Retrieves the current application values from the values service
  - Provides the schema and values to the AI model to apply the requested changes
  - Returns the updated values JSON


  - **request:**
    ```
        POST /message
           { input : "{ user_input }"}
    ```

  - **response:**
    ```
        200 OK -> { new_values } as json
        404 Not Found
        500 Internal Server Error
    ```

  - **arguments:**
    ```
        --listen host:port (default "0.0.0.0:5003")
    ```

  - **example user inputs**:
    ```
        . set tournament service memory to 1024mb
        . set GAME_NAME env to toyblast for matchmaking service
        . lower cpu limit of chat service to %80
    ```

---

## Expectations from the Finished Project

### How to Run

-   Provide a `docker-compose.yml` file that builds and runs all
    services.

-   The entire system should start with a single command:

    ```
    docker compose up
    ```

-   After running the command:

    -   All services should be up and ready to serve requests.
    -   Services should automatically restart if any of them goes down.

-  Run commands like below to test it.
   ```
   curl -X POST http://localhost:5003/message      -H "Content-Type: application/json"      -d '{"input": "set tournament service memory to 1024mb"}'

   curl -X POST http://localhost:5003/message      -H "Content-Type: application/json"      -d '{"input": "set GAME_NAME env to toyblast for matchmaking service"}'

   curl -X POST http://localhost:5003/message      -H "Content-Type: application/json"      -d '{"input": "lower cpu limit of chat service to %80"}'
   ```

------------------------------------------------------------------------

### Implementation Requirements

-   All services must be implemented in **Python**.
-   Selected AI/LLM model must run **locally** using **Ollama**.
-   No external or cloud-based LLM services should be used.
-   The selected LLM should be:
    -   Local-machine friendly
    -   Suitable for generating configuration updates programmatically
-   LLM responses must be **validated against the corresponding JSON
    Schema**.
-   **The chosen model and prompting strategy should ensure reliable and
    correct outputs.**

------------------------------------------------------------------------

### Folder Structure

The finished project is expected to follow this folder structure:
```
  ├── bot-server
  │   └── Dockerfile
  ├── data
  │   ├── schemas
  │   │   ├── chat.schema.json
  │   │   ├── matchmaking.schema.json
  │   │   └── tournament.schema.json
  │   └── values
  │       ├── chat.value.json
  │       ├── matchmaking.value.json
  │       └── tournament.value.json
  ├── docker-compose.yml
  ├── INTERN.md
  ├── README.md
  ├── schema-server
  │   └── Dockerfile
  └── values-server
      └── Dockerfile
```

-   Each service should be containerized and independently runnable.
-   Shared data (schemas and values) should be placed under the `data`
    directory.

------------------------------------------------------------------------

## Documentation Requirements

-   The finished project must include a **INTERN.md** file.
-   The INTERN.md file should clearly explain:
    -   Design decisions (e.g. why a specific LLM model was chosen)
    -   How the system is implemented and structured
    -   How services communicate with each other
    -   The end-to-end flow of a user request
-   Focus on **reasoning and trade-offs**, not just code.

------------------------------------------------------------------------

## Notes

-   Simplicity and clarity are preferred over over-engineering.
-   Reasonable assumptions are allowed as long as they are documented.