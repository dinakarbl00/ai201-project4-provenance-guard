from flask import Flask, request, jsonify
from datetime import datetime, timezone
import json
import uuid
from pathlib import Path

app = Flask(__name__)

LOG_FILE = Path("data/audit_log.json")


def get_timestamp():
    return datetime.now(timezone.utc).isoformat()


def load_log():
    if not LOG_FILE.exists():
        return []

    if LOG_FILE.read_text().strip() == "":
        return []

    return json.loads(LOG_FILE.read_text())


def save_log(entries):
    LOG_FILE.parent.mkdir(exist_ok=True)
    LOG_FILE.write_text(json.dumps(entries, indent=2))


def add_log_entry(entry):
    entries = load_log()
    entries.append(entry)
    save_log(entries)


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Provenance Guard API is running",
        "endpoints": ["/submit", "/log"]
    })


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    text = data.get("text", "").strip()
    creator_id = data.get("creator_id", "").strip()

    if text == "":
        return jsonify({"error": "Missing required field: text"}), 400

    if creator_id == "":
        return jsonify({"error": "Missing required field: creator_id"}), 400

    content_id = str(uuid.uuid4())

    # Placeholder result for now.
    # We will replace this with real detection signals later.
    attribution = "uncertain"
    confidence = 0.50
    label = "We are not sure whether this writing was AI-generated or human-written. The available signals are mixed, so readers should treat this label as uncertain."

    response = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signals": {
            "llm_score": None,
            "stylometric_score": None,
            "repetition_score": None
        },
        "status": "classified"
    }

    log_entry = {
        "event_type": "classification",
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": get_timestamp(),
        "attribution": attribution,
        "confidence": confidence,
        "signals": response["signals"],
        "label": label,
        "status": "classified"
    }

    add_log_entry(log_entry)

    return jsonify(response)


@app.route("/log", methods=["GET"])
def get_log():
    entries = load_log()

    return jsonify({
        "count": len(entries),
        "entries": entries
    })


if __name__ == "__main__":
    app.run(debug=True)