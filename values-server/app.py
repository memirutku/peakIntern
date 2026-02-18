"""
Values Service - Serves current configuration values for applications.

This service provides the current configuration values for application configurations.
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
VALUES_DIR = os.environ.get("VALUES_DIR", "/data/values")

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


def get_values_path_jk(app_name: str) -> str:
    """Get the file path for values based on app name."""
    return os.path.join(VALUES_DIR, f"{app_name}.value.json")


@app.route("/health", methods=["GET"])
def health():
    """
    Health check endpoint with data directory verification.

    Returns 503 if the values directory is not accessible.
    """
    if os.path.isdir(VALUES_DIR) and os.access(VALUES_DIR, os.R_OK):
        logger.info("[HEALTH] status=healthy data_dir=accessible")
        return jsonify({"status": "healthy", "data_dir": "accessible"}), 200
    else:
        logger.warning("[HEALTH] status=unhealthy data_dir=not_accessible")
        return jsonify({"status": "unhealthy", "data_dir": "not accessible"}), 503


@app.route("/<app_name>", methods=["GET"])
def get_values(app_name: str):
    """
    Get current configuration values for a given application.

    Args:
        app_name: The application identifier (e.g., 'chat', 'tournament', 'matchmaking')

    Returns:
        200 OK with JSON values
        400 Bad Request if app_name is invalid
        404 Not Found if values don't exist
        500 Internal Server Error on failure
    """
    # Path traversal protection
    if not validate_app_name(app_name):
        logger.warning(f"[FETCH] app_name={app_name} status=400 reason=invalid_app_name")
        return jsonify({"error": "Invalid application name"}), 400

    values_path = get_values_path_jk(app_name)

    if not os.path.exists(values_path):
        logger.info(f"[FETCH] app_name={app_name} status=404")
        return jsonify({"error": f"Values not found for application: {app_name}"}), 404

    try:
        with open(values_path, "r", encoding="utf-8") as f:
            values = json.load(f)
        logger.info(f"[FETCH] app_name={app_name} status=200")
        return jsonify(values), 200
    except json.JSONDecodeError as e:
        logger.error(f"[FETCH] app_name={app_name} status=500 error=invalid_json")
        return jsonify({"error": f"Invalid JSON in values file: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"[FETCH] app_name={app_name} status=500 error={str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Values Service")
    parser.add_argument(
        "--values-dir",
        default="/data/values",
        dest="values_dir",
        help="Directory containing value files (default: /data/values)"
    )
    parser.add_argument(
        "--listen",
        default="0.0.0.0:5002",
        help="Host and port to listen on (default: 0.0.0.0:5002)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    VALUES_DIR = args.values_dir

    host, port = args.listen.split(":")
    app.run(host=host, port=int(port), debug=False)
