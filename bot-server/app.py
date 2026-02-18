"""
Bot Service - AI-driven configuration management using natural language.

This service accepts natural language user input and uses a local LLM (via Ollama)
to identify the target application and apply configuration changes.
"""

import argparse
import json
import logging
import os
import re
import time
import uuid
import requests
from flask import Flask, jsonify, request, g
from jsonschema import validate, ValidationError

app = Flask(__name__)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Input validation constants
MAX_INPUT_LENGTH = 2000

# Configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
SCHEMA_SERVICE_URL = os.environ.get("SCHEMA_SERVICE_URL", "http://schema-server:5001")
VALUES_SERVICE_URL = os.environ.get("VALUES_SERVICE_URL", "http://values-server:5002")
LLM_MODEL = os.environ.get("LLM_MODEL", "llama3.2")
MAX_RETRIES = 3
# Max tokens for LLM response (default 4096); 1024 often truncates large config JSON
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "4096"))

# Available applications
AVAILABLE_APPS = ["chat", "tournament", "matchmaking"]


def generate_request_id() -> str:
    """Generate a short unique request ID for correlation."""
    return f"req-{uuid.uuid4().hex[:8]}"


def log_event(action: str, message: str = "", app_name: str = None, **kwargs):
    """
    Log a structured event with correlation ID.

    Format: [request_id] [app_name] [action] message key=value ...
    """
    request_id = getattr(g, "request_id", "no-req-id")
    app_label = f"[{app_name}]" if app_name else ""

    extra_parts = " ".join(f"{k}={v}" for k, v in kwargs.items())
    log_message = f"[{request_id}] {app_label} [{action}] {message} {extra_parts}".strip()

    logger.info(log_message)


def check_service_health(url: str, timeout: int = 5) -> tuple[bool, str]:
    """
    Check if a service is healthy.

    Returns:
        Tuple of (is_healthy, status_message)
    """
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return True, "healthy"
        return False, f"unhealthy (status {response.status_code})"
    except requests.ConnectionError:
        return False, "unreachable"
    except requests.Timeout:
        return False, "timeout"
    except Exception as e:
        return False, f"error: {str(e)}"


def handle_request_exception(e: requests.RequestException, service_name: str) -> tuple[dict, int]:
    """
    Handle request exceptions with specific error messages.

    Args:
        e: The exception that occurred
        service_name: Name of the service for error messages

    Returns:
        Tuple of (error_response_dict, http_status_code)
    """
    if isinstance(e, requests.ConnectionError):
        return {"error": f"{service_name} servisine erişilemiyor (connection error)"}, 503
    elif isinstance(e, requests.Timeout):
        return {"error": f"{service_name} isteği zaman aşımına uğradı (timeout)"}, 504
    elif isinstance(e, requests.HTTPError):
        status_code = e.response.status_code if e.response is not None else 500
        if status_code == 404:
            return {"error": f"{service_name}: Kaynak bulunamadı (404)"}, 404
        elif status_code >= 500:
            return {"error": f"{service_name} servis hatası ({status_code})"}, 502
        else:
            return {"error": f"{service_name} hatası: {str(e)}"}, status_code
    else:
        return {"error": f"{service_name} hatası: {str(e)}"}, 500


def call_ollama_jk(prompt: str, timeout: int = 600) -> str:
    """
    Call the Ollama API to generate a response.

    Args:
        prompt: The prompt to send to the LLM
        timeout: Request timeout in seconds

    Returns:
        The generated response text
    """
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": OLLAMA_NUM_PREDICT,
        }
    }

    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()

    result = response.json()
    return result.get("response", "")


def identify_app_name_jk(user_input: str) -> str:
    """
    Use the LLM to identify which application the user wants to modify.

    Args:
        user_input: The natural language input from the user

    Returns:
        The identified application name
    """
    prompt = f"""You are a configuration assistant. Identify which application the user wants to modify.

Available applications: {', '.join(AVAILABLE_APPS)}

User request: "{user_input}"

Respond with ONLY the application name (one of: {', '.join(AVAILABLE_APPS)}). No explanation.
"""

    response = call_ollama_jk(prompt)
    app_name = response.strip().lower()

    # Clean up the response - extract just the app name
    for app in AVAILABLE_APPS:
        if app in app_name:
            return app

    # If no exact match, return the cleaned response
    return app_name


def fetch_schema_jk(app_name: str) -> dict:
    """Fetch the JSON schema for an application from the Schema Service."""
    url = f"{SCHEMA_SERVICE_URL}/{app_name}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_values_jk(app_name: str) -> dict:
    """Fetch the current values for an application from the Values Service."""
    url = f"{VALUES_SERVICE_URL}/{app_name}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def is_json_truncated(json_str: str) -> bool:
    """
    Check if JSON appears to be truncated (incomplete).

    Args:
        json_str: The JSON string to check

    Returns:
        True if JSON appears truncated
    """
    if not json_str:
        return True

    json_str = json_str.strip()
    if not json_str:
        return True

    # Count brackets - if unbalanced, likely truncated
    open_braces = json_str.count("{")
    close_braces = json_str.count("}")
    open_brackets = json_str.count("[")
    close_brackets = json_str.count("]")

    if open_braces != close_braces or open_brackets != close_brackets:
        return True

    # Check if it ends properly
    if json_str.startswith("{") and not json_str.endswith("}"):
        return True
    if json_str.startswith("[") and not json_str.endswith("]"):
        return True

    return False


def try_recover_truncated_json(json_str: str) -> str:
    """
    Attempt to recover truncated JSON by closing open brackets/braces.

    This is a best-effort recovery for cases where LLM token limit
    caused truncation.

    Args:
        json_str: The potentially truncated JSON

    Returns:
        Recovered JSON string (may still be invalid)
    """
    if not json_str:
        return json_str

    json_str = json_str.strip()

    # Remove trailing incomplete elements (comma, colon, etc.)
    while json_str and json_str[-1] in ",: \n\t\r":
        json_str = json_str[:-1]

    # Count and close brackets
    open_braces = json_str.count("{") - json_str.count("}")
    open_brackets = json_str.count("[") - json_str.count("]")

    # Close open structures (inner first)
    json_str += "]" * max(0, open_brackets)
    json_str += "}" * max(0, open_braces)

    return json_str


def extract_json_from_response_jk(response: str) -> str:
    """
    Extract JSON from LLM response, handling markdown code blocks.

    Args:
        response: The raw LLM response

    Returns:
        Extracted JSON string
    """
    # Try to find JSON in code blocks first
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    matches = re.findall(code_block_pattern, response)
    if matches:
        extracted = matches[0].strip()
        if is_json_truncated(extracted):
            log_event("JSON_TRUNCATED", "Detected truncated JSON in code block, attempting recovery")
            extracted = try_recover_truncated_json(extracted)
        return extracted

    # Try to find raw JSON (starts with { and ends with })
    json_pattern = r"\{[\s\S]*\}"
    matches = re.findall(json_pattern, response)
    if matches:
        # Return the longest match (likely the full JSON)
        extracted = max(matches, key=len)
        if is_json_truncated(extracted):
            log_event("JSON_TRUNCATED", "Detected truncated raw JSON, attempting recovery")
            extracted = try_recover_truncated_json(extracted)
        return extracted

    # Last resort: if response starts with {, try to recover it
    stripped = response.strip()
    if stripped.startswith("{"):
        log_event("JSON_PARTIAL", "Response starts with { but no complete JSON found, attempting recovery")
        return try_recover_truncated_json(stripped)

    return response.strip()


def generate_updated_values_jk(user_input: str, schema: dict, current_values: dict, app_name: str) -> dict:
    """
    Use the LLM to generate updated configuration values based on user input.

    Args:
        user_input: The natural language input from the user
        schema: The JSON schema for validation
        current_values: The current configuration values
        app_name: The application name

    Returns:
        Updated configuration values as a dictionary
    """
    # NOTE: Schema removed from prompt to reduce token count (~67KB saved).
    # Validation is still performed after LLM response via validate_against_schema_jk().
    prompt = f"""You are a configuration assistant. Modify the current configuration based on the user's request.

Application: {app_name}

User request: "{user_input}"

Current configuration (JSON):
{json.dumps(current_values, indent=2)}

Instructions:
1. Modify ONLY the field(s) mentioned in the user request
2. Keep all other values exactly the same
3. For memory: use "limitMiB" and "requestMiB" under resources.memory
4. For CPU: use "limitMilliCPU" and "requestMilliCPU" under resources.cpu (1000 = 1 core)
5. For env vars: use "envs" field under the container

Respond with ONLY the complete updated JSON. No explanation or markdown.
"""

    response = call_ollama_jk(prompt)
    json_str = extract_json_from_response_jk(response)
    if not json_str or not json_str.strip():
        log_event(
            "LLM_EMPTY_RESPONSE",
            f"raw_length={len(response)}",
            snippet=(response[:200] + "..." if len(response) > 200 else response),
        )
        raise ValueError("LLM response was empty or contained no JSON")
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        log_event(
            "LLM_INVALID_JSON",
            f"raw_length={len(response)} extracted_length={len(json_str)}",
            snippet=(json_str[:200] + "..." if len(json_str) > 200 else json_str),
            error=str(e),
        )
        raise


def validate_against_schema_jk(values: dict, schema: dict) -> bool:
    """
    Validate values against a JSON schema.

    Args:
        values: The values to validate
        schema: The JSON schema

    Returns:
        True if valid, raises ValidationError otherwise
    """
    validate(instance=values, schema=schema)
    return True


@app.route("/health", methods=["GET"])
def health():
    """
    Health check endpoint with dependency status.

    Returns status: healthy, degraded, or unhealthy based on dependencies.
    """
    dependencies = {}

    # Check Ollama
    ollama_healthy, ollama_status = check_service_health(f"{OLLAMA_URL}/api/tags")
    dependencies["ollama"] = ollama_status

    # Check Schema Service
    schema_healthy, schema_status = check_service_health(f"{SCHEMA_SERVICE_URL}/chat")
    dependencies["schema_service"] = schema_status

    # Check Values Service
    values_healthy, values_status = check_service_health(f"{VALUES_SERVICE_URL}/chat")
    dependencies["values_service"] = values_status

    # Determine overall status
    all_healthy = ollama_healthy and schema_healthy and values_healthy
    any_healthy = ollama_healthy or schema_healthy or values_healthy

    if all_healthy:
        status = "healthy"
        http_code = 200
    elif any_healthy:
        status = "degraded"
        http_code = 200
    else:
        status = "unhealthy"
        http_code = 503

    return jsonify({
        "status": status,
        "dependencies": dependencies
    }), http_code


@app.route("/message", methods=["POST"])
def process_message():
    """
    Process a natural language configuration request.

    Request body:
        {"input": "user's natural language request"}

    Returns:
        200 OK with updated configuration JSON
        400 Bad Request if input is invalid
        404 Not Found if application not found
        500 Internal Server Error on failure
    """
    # Generate correlation ID for this request
    g.request_id = generate_request_id()
    request_start = time.time()

    try:
        data = request.get_json()
        if not data or "input" not in data:
            log_event("VALIDATION_ERROR", "Missing 'input' field")
            return jsonify({"error": "Missing 'input' field in request body"}), 400

        user_input = data["input"]

        # Input validation
        if not isinstance(user_input, str):
            log_event("VALIDATION_ERROR", "Input is not a string")
            return jsonify({"error": "Input must be a string"}), 400

        user_input = user_input.strip()

        if not user_input:
            log_event("VALIDATION_ERROR", "Empty input")
            return jsonify({"error": "Input cannot be empty"}), 400

        if len(user_input) > MAX_INPUT_LENGTH:
            log_event("VALIDATION_ERROR", f"Input too long: {len(user_input)} chars")
            return jsonify({
                "error": f"Input too long. Maximum {MAX_INPUT_LENGTH} characters allowed"
            }), 400

        log_event("START", f"user_input=\"{user_input[:100]}{'...' if len(user_input) > 100 else ''}\"")

        # Step 1: Identify the application name using LLM
        llm_start = time.time()
        try:
            app_name = identify_app_name_jk(user_input)
        except requests.RequestException as e:
            log_event("LLM_ERROR", "Failed to contact Ollama for app identification")
            error_response, status_code = handle_request_exception(e, "Ollama")
            return jsonify(error_response), status_code

        llm_duration = time.time() - llm_start
        log_event("LLM_IDENTIFY", app_name=app_name, duration=f"{llm_duration:.2f}s")

        if app_name not in AVAILABLE_APPS:
            log_event("APP_NOT_FOUND", f"Identified '{app_name}' not in available apps")
            return jsonify({
                "error": f"Could not identify application. Available apps: {', '.join(AVAILABLE_APPS)}"
            }), 404

        # Step 2: Fetch schema from Schema Service
        try:
            schema = fetch_schema_jk(app_name)
            log_event("FETCH_SCHEMA", "success", app_name=app_name)
        except requests.RequestException as e:
            log_event("FETCH_SCHEMA", "failed", app_name=app_name, error=str(e))
            error_response, status_code = handle_request_exception(e, "Schema Service")
            return jsonify(error_response), status_code

        # Step 3: Fetch current values from Values Service
        try:
            current_values = fetch_values_jk(app_name)
            log_event("FETCH_VALUES", "success", app_name=app_name)
        except requests.RequestException as e:
            log_event("FETCH_VALUES", "failed", app_name=app_name, error=str(e))
            error_response, status_code = handle_request_exception(e, "Values Service")
            return jsonify(error_response), status_code

        # Step 4 & 5 & 6: Generate updated values with retry mechanism and exponential backoff
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                llm_start = time.time()
                # Generate updated values using LLM
                updated_values = generate_updated_values_jk(
                    user_input, schema, current_values, app_name
                )
                llm_duration = time.time() - llm_start
                log_event("LLM_UPDATE", app_name=app_name, attempt=attempt + 1, duration=f"{llm_duration:.2f}s")

                # Validate against schema
                validate_against_schema_jk(updated_values, schema)
                log_event("VALIDATE", "success", app_name=app_name)

                # Success - return the updated values
                total_duration = time.time() - request_start
                log_event("END", app_name=app_name, status=200, total_duration=f"{total_duration:.2f}s")
                return jsonify(updated_values), 200

            except json.JSONDecodeError as e:
                last_error = f"Invalid JSON response from LLM (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}"
                log_event("LLM_JSON_ERROR", app_name=app_name, attempt=attempt + 1, error=str(e))
            except ValidationError as e:
                last_error = f"Schema validation failed (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}"
                log_event("VALIDATION_FAILED", app_name=app_name, attempt=attempt + 1, error=str(e)[:200])
            except requests.RequestException as e:
                log_event("LLM_REQUEST_ERROR", app_name=app_name, attempt=attempt + 1, error=str(e))
                # For LLM request errors, use handle_request_exception
                error_response, status_code = handle_request_exception(e, "Ollama")
                last_error = error_response["error"]
            except Exception as e:
                last_error = f"Error generating values (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}"
                log_event("LLM_ERROR", app_name=app_name, attempt=attempt + 1, error=str(e))

            # Exponential backoff before next retry (skip on last attempt)
            if attempt < MAX_RETRIES - 1:
                wait_time = 2 ** attempt  # 1, 2, 4 seconds
                log_event("RETRY_BACKOFF", app_name=app_name, wait_seconds=wait_time)
                time.sleep(wait_time)

        # All retries failed
        total_duration = time.time() - request_start
        log_event("END", app_name=app_name, status=500, total_duration=f"{total_duration:.2f}s", error="max_retries_exceeded")
        return jsonify({"error": f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}"}), 500

    except Exception as e:
        total_duration = time.time() - request_start
        log_event("END", status=500, total_duration=f"{total_duration:.2f}s", error=str(e))
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Bot Service")
    parser.add_argument(
        "--listen",
        default="0.0.0.0:5003",
        help="Host and port to listen on (default: 0.0.0.0:5003)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    host, port = args.listen.split(":")
    app.run(host=host, port=int(port), debug=False)
