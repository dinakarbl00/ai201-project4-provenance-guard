from flask import Flask, request, jsonify
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq
import json
import uuid
import os
import re
from pathlib import Path
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

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
        "endpoints": ["/submit", "/appeal", "/log"]
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

        attribution = get_attribution_from_score(score)

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

def get_attribution_from_score(score):
    if score >= 0.75:
        return "likely_ai"

    if score <= 0.44:
        return "likely_human"

    return "uncertain"

def get_stylometric_signal(text):
    words = re.findall(r"[a-zA-Z']+", text.lower())
    sentences = [
        sentence.strip()
        for sentence in re.split(r"[.!?]+", text)
        if sentence.strip()
    ]

    if len(words) < 20 or len(sentences) < 2:
        return {
            "stylometric_score": 0.50,
            "stylometric_details": {
                "reason": "Text is too short for reliable stylometric analysis."
            }
        }

    sentence_lengths = []

    for sentence in sentences:
        sentence_words = re.findall(r"[a-zA-Z']+", sentence.lower())
        sentence_lengths.append(len(sentence_words))

    average_length = sum(sentence_lengths) / len(sentence_lengths)

    variance = sum(
        (length - average_length) ** 2
        for length in sentence_lengths
    ) / len(sentence_lengths)

    unique_words = set(words)
    type_token_ratio = len(unique_words) / len(words)

    punctuation_count = len(re.findall(r"[,.!?;:]", text))
    punctuation_density = punctuation_count / max(len(words), 1)

    # Lower sentence variance usually means the writing is more uniform.
    if variance < 8:
        sentence_uniformity_score = 0.85
    elif variance < 20:
        sentence_uniformity_score = 0.65
    elif variance < 40:
        sentence_uniformity_score = 0.45
    else:
        sentence_uniformity_score = 0.25

    # Lower vocabulary diversity can suggest more generic writing.
    if type_token_ratio < 0.45:
        vocabulary_score = 0.80
    elif type_token_ratio < 0.60:
        vocabulary_score = 0.60
    elif type_token_ratio < 0.75:
        vocabulary_score = 0.40
    else:
        vocabulary_score = 0.25

    # Very controlled punctuation can look more AI-like.
    if punctuation_density < 0.03:
        punctuation_score = 0.65
    elif punctuation_density < 0.08:
        punctuation_score = 0.45
    else:
        punctuation_score = 0.25

    stylometric_score = (
        0.50 * sentence_uniformity_score
        + 0.30 * vocabulary_score
        + 0.20 * punctuation_score
    )

    return {
        "stylometric_score": round(stylometric_score, 2),
        "stylometric_details": {
            "sentence_count": len(sentences),
            "word_count": len(words),
            "sentence_length_variance": round(variance, 2),
            "type_token_ratio": round(type_token_ratio, 2),
            "punctuation_density": round(punctuation_density, 2)
        }
    }

def get_repetition_signal(text):
    lower_text = text.lower()

    generic_phrases = [
        "it is important to note",
        "furthermore",
        "in conclusion",
        "overall",
        "plays a crucial role",
        "transformative",
        "various sectors",
        "responsible deployment",
        "ethical implications",
        "paradigm shift"
    ]

    phrase_hits = []

    for phrase in generic_phrases:
        if phrase in lower_text:
            phrase_hits.append(phrase)

    words = re.findall(r"[a-zA-Z']+", lower_text)

    repeated_words = []

    for word in set(words):
        if len(word) > 5 and words.count(word) >= 3:
            repeated_words.append(word)

    phrase_score = min(len(phrase_hits) * 0.18, 0.80)
    repeated_word_score = min(len(repeated_words) * 0.08, 0.20)

    repetition_score = phrase_score + repeated_word_score
    repetition_score = max(0.05, min(repetition_score, 1.0))

    return {
        "repetition_score": round(repetition_score, 2),
        "repetition_details": {
            "generic_phrase_hits": phrase_hits,
            "repeated_words": repeated_words
        }
    }

def combine_scores(llm_score, stylometric_score, repetition_score):
    combined_score = (
        0.50 * llm_score
        + 0.35 * stylometric_score
        + 0.15 * repetition_score
    )

    return round(combined_score, 2)

def find_classification_entry(entries, content_id):
    for entry in entries:
        if (
            entry.get("event_type") == "classification"
            and entry.get("content_id") == content_id
        ):
            return entry

    return None

@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
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
    stylometric_result = get_stylometric_signal(text)
    repetition_result = get_repetition_signal(text)

    confidence = combine_scores(
        llm_result["llm_score"],
        stylometric_result["stylometric_score"],
        repetition_result["repetition_score"]
    )

    attribution = get_attribution_from_score(confidence)
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
            "stylometric_score": stylometric_result["stylometric_score"],
            "stylometric_details": stylometric_result["stylometric_details"],
            "repetition_score": repetition_result["repetition_score"],
            "repetition_details": repetition_result["repetition_details"]
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

@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    content_id = data.get("content_id", "").strip()
    creator_reasoning = data.get("creator_reasoning", "").strip()

    if content_id == "":
        return jsonify({"error": "Missing required field: content_id"}), 400

    if creator_reasoning == "":
        return jsonify({"error": "Missing required field: creator_reasoning"}), 400

    entries = load_log()
    original_entry = find_classification_entry(entries, content_id)

    if original_entry is None:
        return jsonify({"error": "No classified content found for that content_id"}), 404

    original_entry["status"] = "under_review"
    original_entry["appeal_filed"] = True

    appeal_entry = {
        "event_type": "appeal",
        "content_id": content_id,
        "creator_id": original_entry.get("creator_id"),
        "timestamp": get_timestamp(),
        "status": "under_review",
        "appeal_reasoning": creator_reasoning,
        "original_attribution": original_entry.get("attribution"),
        "original_confidence": original_entry.get("confidence"),
        "original_signals": original_entry.get("signals")
    }

    entries.append(appeal_entry)
    save_log(entries)

    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Appeal received. This content is now under review.",
        "appeal": {
            "creator_reasoning": creator_reasoning,
            "original_attribution": original_entry.get("attribution"),
            "original_confidence": original_entry.get("confidence")
        }
    })

@app.route("/log", methods=["GET"])
def get_log():
    entries = load_log()

    return jsonify({
        "count": len(entries),
        "entries": entries
    })


if __name__ == "__main__":
    app.run(debug=True)