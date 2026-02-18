"""
Schema Service - Serves JSON Schemas for applications.

This service provides JSON Schema definitions for application configurations.
Each application is identified by an app_name parameter.
"""

import argparse
import json
import logging
import os
import re
from flask import Flask, jsonify

app = Flask(__name__)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Configuration defaults
SCHEMA_DIR = os.environ.get("SCHEMA_DIR", "/data/schemas")

# Input validation pattern - only alphanumeric, hyphen, underscore
APP_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_app_name(app_name: str) -> bool:
    """
    Validate app_name to prevent path traversal attacks.

    Only allows alphanumeric characters, hyphens, and underscores.

    Args:
        app_name: The application name to validate

    Returns:
        True if valid, False otherwise
    """
    if not app_name:
        return False
    if len(app_name) > 64:  # Reasonable length limit
        return False
    return bool(APP_NAME_PATTERN.match(app_name))


def get_schema_path_jk(app_name: str) -> str:
    """Get the file path for a schema based on app name."""
    return os.path.join(SCHEMA_DIR, f"{app_name}.schema.json")


@app.route("/health", methods=["GET"])
def health():
    """
    Health check endpoint with data directory verification.

    Returns 503 if the schema directory is not accessible.
    """
    if os.path.isdir(SCHEMA_DIR) and os.access(SCHEMA_DIR, os.R_OK):
        logger.info("[HEALTH] status=healthy data_dir=accessible")
        return jsonify({"status": "healthy", "data_dir": "accessible"}), 200
    else:
        logger.warning("[HEALTH] status=unhealthy data_dir=not_accessible")
        return jsonify({"status": "unhealthy", "data_dir": "not accessible"}), 503


@app.route("/<app_name>", methods=["GET"])
def get_schema(app_name: str):
    """
    Get JSON Schema for a given application.

    Args:
        app_name: The application identifier (e.g., 'chat', 'tournament', 'matchmaking')

    Returns:
        200 OK with JSON schema
        400 Bad Request if app_name is invalid
        404 Not Found if schema doesn't exist
        500 Internal Server Error on failure
    """
    # Path traversal protection
    if not validate_app_name(app_name):
        logger.warning(f"[FETCH] app_name={app_name} status=400 reason=invalid_app_name")
        return jsonify({"error": "Invalid application name"}), 400

    schema_path = get_schema_path_jk(app_name)

    if not os.path.exists(schema_path):
        logger.info(f"[FETCH] app_name={app_name} status=404")
        return jsonify({"error": f"Schema not found for application: {app_name}"}), 404

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        logger.info(f"[FETCH] app_name={app_name} status=200")
        return jsonify(schema), 200
    except json.JSONDecodeError as e:
        logger.error(f"[FETCH] app_name={app_name} status=500 error=invalid_json")
        return jsonify({"error": f"Invalid JSON in schema file: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"[FETCH] app_name={app_name} status=500 error={str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Schema Service")
    parser.add_argument(
        "--schema-dir",
        default="/data/schemas",
        help="Directory containing schema files (default: /data/schemas)"
    )
    parser.add_argument(
        "--listen",
        default="0.0.0.0:5001",
        help="Host and port to listen on (default: 0.0.0.0:5001)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    SCHEMA_DIR = args.schema_dir

    host, port = args.listen.split(":")
    app.run(host=host, port=int(port), debug=False)
