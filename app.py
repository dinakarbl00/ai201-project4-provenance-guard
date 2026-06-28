from flask import Flask, request, jsonify
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq
import json
import uuid
import os
from pathlib import Path

app = Flask(__name__)

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")

if groq_api_key:
    groq_client = Groq(api_key=groq_api_key)
else:
    groq_client = None

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

def extract_json_from_text(text):
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response")

    json_text = text[start:end + 1]
    return json.loads(json_text)

def get_llm_signal(text):
    if groq_client is None:
        return {
            "llm_score": 0.50,
            "llm_attribution": "uncertain",
            "llm_reasoning": "Groq API key was not found, so the LLM signal could not run."
        }

    prompt = f"""
        You are helping a writing platform estimate whether a submitted text appears AI-generated or human-written.

        Return only valid JSON with these exact keys:
        - ai_score: a number from 0.0 to 1.0, where 1.0 means very likely AI-generated and 0.0 means very likely human-written
        - attribution: one of likely_ai, uncertain, likely_human
        - reasoning: one short plain-English explanation

        Use uncertainty carefully. Do not overclaim. Formal human writing and non-native English writing should not automatically be treated as AI-generated.

        Text to analyze:
        {text}
        """

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a careful AI writing attribution assistant. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=300
        )

        model_text = response.choices[0].message.content
        parsed = extract_json_from_text(model_text)

        score = float(parsed.get("ai_score", 0.50))
        score = max(0.0, min(1.0, score))

        attribution = parsed.get("attribution", "uncertain")

        if attribution not in ["likely_ai", "uncertain", "likely_human"]:
            if score >= 0.75:
                attribution = "likely_ai"
            elif score <= 0.44:
                attribution = "likely_human"
            else:
                attribution = "uncertain"

        return {
            "llm_score": round(score, 2),
            "llm_attribution": attribution,
            "llm_reasoning": parsed.get("reasoning", "No reasoning provided.")
        }

    except Exception as error:
        return {
            "llm_score": 0.50,
            "llm_attribution": "uncertain",
            "llm_reasoning": f"Groq signal failed: {str(error)}"
        }

def get_label(attribution):
    if attribution == "likely_ai":
        return "This writing shows strong signs of being AI-generated. The platform is showing this label so readers have more context, but the creator may appeal this decision."

    if attribution == "likely_human":
        return "This writing shows stronger signs of being written by a person. No AI-generated label is being applied based on the current review."

    return "We are not sure whether this writing was AI-generated or human-written. The available signals are mixed, so readers should treat this label as uncertain."

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

    llm_result = get_llm_signal(text)

    attribution = llm_result["llm_attribution"]
    confidence = llm_result["llm_score"]
    label = get_label(attribution)

    response = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signals": {
            "llm_score": llm_result["llm_score"],
            "llm_reasoning": llm_result["llm_reasoning"],
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