# Provenance Guard

Provenance Guard is a Flask backend system for a creative writing platform. It accepts submitted writing, analyzes whether the content appears AI-generated, human-written, or uncertain, returns a confidence score, displays a plain-language transparency label, stores a structured audit log, and allows creators to appeal a classification.

The goal of this project is not to claim perfect AI detection. AI-content detection is uncertain, especially for short writing, formal human writing, and non-native English writing. Because of that, this system is designed to communicate uncertainty clearly, avoid overclaiming, and provide an appeals workflow for creators.

---

## Setup Instructions

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```text
GROQ_API_KEY=your_groq_api_key_here
```

Run the Flask server:

```powershell
python app.py
```

The app runs locally at:

```text
http://127.0.0.1:5000
```

---

## API Endpoints


| Method | Endpoint           | Purpose                                                 |
| ------ | ------------------ | ------------------------------------------------------- |
| `GET`  | `/`                | Health check and endpoint list                          |
| `POST` | `/submit`          | Submit text for attribution analysis                    |
| `POST` | `/appeal`          | Submit an appeal for a classification                   |
| `GET`  | `/log`             | View structured audit log entries                       |
| `POST` | `/verify-human`    | Add a provenance certificate after creator verification |
| `GET`  | `/analytics`       | View detection and appeal metrics                       |
| `POST` | `/submit-metadata` | Analyze structured metadata as a second content type    |


---

## Architecture Overview

A text submission moves through the system in this order:

```text
Client / Writing Platform
        |
        | POST /submit
        | { text, creator_id }
        v
Flask API
        |
        | validate request
        | create content_id
        v
Multi-Signal Detection Pipeline
        |
        |-- Signal 1: Groq LLM score
        |-- Signal 2: Stylometric score
        |-- Signal 3: Repetition / generic phrase score
        v
Confidence Scoring Layer
        |
        | combine signal scores using weighted ensemble
        v
Transparency Label Generator
        |
        | map attribution + confidence to plain-language label
        v
Audit Log
        |
        | save structured JSON entry with timestamp,
        | content_id, attribution, confidence, signal scores,
        | label text, and status
        v
JSON API Response
```

The appeal flow works separately:

```text
Creator
        |
        | POST /appeal
        | { content_id, creator_reasoning }
        v
Flask API
        |
        | find original classification
        v
Status Update
        |
        | status becomes "under_review"
        v
Audit Log
        |
        | save appeal entry with creator reasoning,
        | original result, original confidence,
        | timestamp, and updated status
        v
JSON API Response
```

---

## Content Submission Endpoint

The `POST /submit` endpoint accepts a JSON body with text and a creator ID.

Example request:

```powershell
$body = @{
    text = "The submitted writing goes here."
    creator_id = "creator-123"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri http://127.0.0.1:5000/submit `
    -Method Post `
    -ContentType "application/json" `
    -Body $body | ConvertTo-Json -Depth 8
```

The response includes:

- `content_id`
- `creator_id`
- `attribution`
- `confidence`
- `label`
- individual signal scores
- `status`

Example response shape:

```json
{
  "content_id": "a98fead7-3e47-4ff3-a15e-087ecc25ff05",
  "creator_id": "test-strong-ai",
  "attribution": "likely_ai",
  "confidence": 0.78,
  "label": "This writing shows strong signs of being AI-generated. The platform is showing this label so readers have more context, but the creator may appeal this decision.",
  "signals": {
    "llm_score": 0.8,
    "stylometric_score": 0.66,
    "repetition_score": 1.0
  },
  "status": "classified"
}
```

---

## Detection Signals

The system uses **three distinct detection signals**. This satisfies the multi-signal requirement and also implements the ensemble detection stretch feature.

---

### Signal 1: Groq LLM Score

The Groq signal asks `llama-3.3-70b-versatile` to estimate whether the submitted text appears AI-generated or human-written.

**What it measures**

This signal measures the overall semantic and stylistic feel of the writing. It looks for broad patterns such as polished structure, generic wording, formulaic phrasing, and lack of personal specificity.

**Why I chose it**

A language model can notice high-level writing patterns that are difficult to capture with simple rules. For example, it can recognize when a paragraph sounds generic, overly balanced, or like a standard AI explanation.

**What it misses**

The LLM can misclassify formal human writing as AI-generated. It can also miss AI-generated writing that has been heavily edited by a human. Because of this, the LLM score is not used alone.

---

### Signal 2: Stylometric Score

The stylometric signal uses Python heuristics to measure structural properties of the text.

It calculates:

- Sentence length variance
- Type-token ratio, which measures vocabulary diversity
- Punctuation density

**What it measures**

This signal measures the shape of the writing rather than the meaning. AI-generated writing often has more uniform sentence lengths and smoother structure. Human writing may be more uneven, especially in casual writing.

**Why I chose it**

This signal is independent from the LLM. It does not ask another model for an opinion. It uses measurable properties of the submitted text, which makes the pipeline more explainable.

**What it misses**

Stylometric scoring is weaker on short submissions because there may not be enough sentences to measure. It can also misread poems, academic writing, or non-native English writing because those styles may be structured, repetitive, or unusually formal.

---

### Signal 3: Repetition and Generic Phrase Score

The repetition signal checks for repeated words and common generic phrases.

Examples of phrases checked:

- `it is important to note`
- `furthermore`
- `in conclusion`
- `overall`
- `plays a crucial role`
- `transformative`
- `various sectors`
- `responsible deployment`

**What it measures**

This signal measures whether the writing relies on repeated transitions, filler wording, or broad phrases often found in AI-generated writing.

**Why I chose it**

This signal is simple, transparent, and easy to explain in the API response. It also helps identify text that repeats the same phrase structure many times.

**What it misses**

Some human academic or professional writing naturally uses transition phrases like `furthermore` or `in conclusion`. This signal can create false positives if used too strongly, so it has the lowest weight in the ensemble.

---

## Confidence Scoring

Each signal returns an AI-likelihood score from `0.0` to `1.0`.

The final score is calculated using this weighted ensemble:

```text
combined_ai_score =
  (0.50 * llm_score)
+ (0.35 * stylometric_score)
+ (0.15 * repetition_score)
```

### Why these weights?

The LLM score receives the highest weight because it captures the broadest judgment. The stylometric score receives a strong weight because it is independent and measurable. The repetition score receives the lowest weight because it is useful but easier to fool and more likely to flag formal human writing.

### Thresholds


| Score Range   | Attribution    | Meaning                              |
| ------------- | -------------- | ------------------------------------ |
| `0.00 - 0.44` | `likely_human` | Stronger signs of human writing      |
| `0.45 - 0.74` | `uncertain`    | Mixed or weak evidence               |
| `0.75 - 1.00` | `likely_ai`    | Strong signs of AI-generated writing |


The uncertain range is intentionally wide because false positives are harmful on a writing platform. If the signals disagree, the system should avoid making a strong claim.

---

## Confidence Validation Examples

I tested the scoring system using inputs that should produce different scores: a highly repetitive AI-like example, a mixed formal example, and a casual human-like example.

---

### High-confidence AI Case

Input:

```text
It is important to note that artificial intelligence plays a crucial role in modern society. Furthermore, artificial intelligence plays a crucial role in business innovation. Overall, artificial intelligence plays a crucial role in responsible deployment. In conclusion, artificial intelligence plays a crucial role across various sectors.
```

Output:

```json
{
  "attribution": "likely_ai",
  "confidence": 0.78,
  "content_id": "a98fead7-3e47-4ff3-a15e-087ecc25ff05",
  "creator_id": "test-strong-ai",
  "label": "This writing shows strong signs of being AI-generated. The platform is showing this label so readers have more context, but the creator may appeal this decision.",
  "signals": {
    "llm_score": 0.8,
    "stylometric_score": 0.66,
    "repetition_score": 1.0
  },
  "status": "classified"
}
```

This produced a high-confidence AI result because all three signals were high. The repetition score was especially high due to repeated use of phrases such as `plays a crucial role`.

---

### Lower-confidence / Uncertain Case

Input:

```text
Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.
```

Output:

```json
{
  "attribution": "uncertain",
  "confidence": 0.59,
  "content_id": "422f00d1-2a58-4393-9759-db3d078df3f5",
  "creator_id": "test-ai-ensemble",
  "label": "We are not sure whether this writing was AI-generated or human-written. The available signals are mixed, so readers should treat this label as uncertain.",
  "signals": {
    "llm_score": 0.7,
    "stylometric_score": 0.35,
    "repetition_score": 0.8
  },
  "status": "classified"
}
```

This result shows uncertainty. The LLM and repetition signals were high, but the stylometric signal was lower. Because the signals disagreed, the combined score stayed in the uncertain range.

---

### High-confidence Human Case

Input:

```text
ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there
```

Output:

```json
{
  "attribution": "likely_human",
  "confidence": 0.21,
  "content_id": "03c92d10-ad64-4083-8ab6-4fa57172580e",
  "creator_id": "test-human-ensemble",
  "label": "This writing shows stronger signs of being written by a person. No AI-generated label is being applied based on the current review.",
  "signals": {
    "llm_score": 0.2,
    "stylometric_score": 0.29,
    "repetition_score": 0.05
  },
  "status": "classified"
}
```

This produced a likely-human result because the writing is casual, personal, irregular, and does not use generic AI-like phrases.

---

## Transparency Labels

The API returns one of the following exact label texts.


| Result Type           | Score Range   | Exact Label Text                                                                                                                                                      |
| --------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| High-confidence AI    | `0.75 - 1.00` | `"This writing shows strong signs of being AI-generated. The platform is showing this label so readers have more context, but the creator may appeal this decision."` |
| Uncertain             | `0.45 - 0.74` | `"We are not sure whether this writing was AI-generated or human-written. The available signals are mixed, so readers should treat this label as uncertain."`         |
| High-confidence human | `0.00 - 0.44` | `"This writing shows stronger signs of being written by a person. No AI-generated label is being applied based on the current review."`                               |


The labels are intentionally written in plain language. They do not use technical terms like classifier, logits, or model probability. The label text also changes between high-confidence AI, uncertain, and high-confidence human cases.

The verified certificate stretch feature uses this additional label:

```text
"Verified human-created work: the creator completed an additional verification step for this submission."
```

---

## Appeals Workflow

Creators can appeal a classification using `POST /appeal`.

Example request:

```powershell
$body = @{
    content_id = "422f00d1-2a58-4393-9759-db3d078df3f5"
    creator_reasoning = "I wrote this myself and the topic is formal, so the writing may sound polished. I want a human reviewer to check the decision."
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri http://127.0.0.1:5000/appeal `
    -Method Post `
    -ContentType "application/json" `
    -Body $body | ConvertTo-Json -Depth 6
```

Example response:

```json
{
  "appeal": {
    "creator_reasoning": "I wrote this myself and the topic is formal, so the writing may sound polished. I want a human reviewer to check the decision.",
    "original_attribution": "uncertain",
    "original_confidence": 0.59
  },
  "content_id": "422f00d1-2a58-4393-9759-db3d078df3f5",
  "message": "Appeal received. This content is now under review.",
  "status": "under_review"
}
```

When an appeal is submitted:

1. The system finds the original classification by `content_id`.
2. The original entry status changes to `under_review`.
3. The original entry gets `appeal_filed: true`.
4. A new appeal entry is added to the audit log with creator reasoning.
5. The API returns a confirmation response.

---

## Rate Limiting

The `POST /submit` endpoint is rate-limited using Flask-Limiter.

Chosen limits:

```text
10 requests per minute
100 requests per day
```

Reasoning:

A real writer may submit several drafts while editing, so 10 submissions per minute allows normal use. However, a writing platform also needs protection from scripts repeatedly submitting content. The 100-per-day limit is high enough for normal creator behavior but low enough to reduce abuse.

Rate limit test output:

```text
Request 1 -> 200
Request 2 -> 200
Request 3 -> 200
Request 4 -> 200
Request 5 -> 200
Request 6 -> 200
Request 7 -> 200
Request 8 -> 200
Request 9 -> 200
Request 10 -> 200
Request 11 -> 429
Request 12 -> 429
```

The `429` responses show that the limit is working.

---

## Audit Log

The audit log is stored as structured JSON in:

```text
data/audit_log.json
```

It can also be viewed through:

```text
GET /log
```

Each classification entry includes:

- `event_type`
- `content_id`
- `creator_id`
- `timestamp`
- `attribution`
- `confidence`
- signal scores
- label text
- status

Example classification entry:

```json
{
  "event_type": "classification",
  "content_id": "a98fead7-3e47-4ff3-a15e-087ecc25ff05",
  "creator_id": "test-strong-ai",
  "timestamp": "2026-06-28T...",
  "attribution": "likely_ai",
  "confidence": 0.78,
  "signals": {
    "llm_score": 0.8,
    "stylometric_score": 0.66,
    "repetition_score": 1.0
  },
  "label": "This writing shows strong signs of being AI-generated. The platform is showing this label so readers have more context, but the creator may appeal this decision.",
  "status": "classified"
}
```

Example appeal entry:

```json
{
  "event_type": "appeal",
  "content_id": "422f00d1-2a58-4393-9759-db3d078df3f5",
  "creator_id": "test-ai-ensemble",
  "timestamp": "2026-06-28T...",
  "status": "under_review",
  "appeal_reasoning": "I wrote this myself and the topic is formal, so the writing may sound polished. I want a human reviewer to check the decision.",
  "original_attribution": "uncertain",
  "original_confidence": 0.59
}
```

This satisfies the requirement for a structured audit log with classification results, confidence scores, timestamps, and appeals.

---

## Stretch Feature: Ensemble Detection

The project implements an ensemble pipeline with three signals:

1. Groq LLM score
2. Stylometric score
3. Repetition / generic phrase score

The weighted strategy is:

```text
50% Groq LLM score
35% stylometric score
15% repetition score
```

Conflicts between signals are resolved through the weighted average. If one signal strongly suggests AI but another does not, the final score often lands in the uncertain range. This avoids automatically applying a high-confidence AI label when the evidence is mixed.

---

## Stretch Feature: Provenance Certificate

The `POST /verify-human` endpoint allows a creator to complete an additional verification step.

Example response:

```json
{
  "content_id": "03c92d10-ad64-4083-8ab6-4fa57172580e",
  "creator_id": "test-human-ensemble",
  "label": "Verified human-created work: the creator completed an additional verification step for this submission.",
  "message": "Verification received. A provenance certificate has been added to this content.",
  "status": "verified_human",
  "verified_human": true
}
```

The certificate label is different from the standard transparency labels. It shows that the creator completed an extra verification step for that submission.

---

## Stretch Feature: Analytics Dashboard

The `GET /analytics` endpoint returns dashboard-style metrics.

Example output:

```json
{
  "appeal_count": 1,
  "appeal_rate": 0.06,
  "average_confidence": 0.36,
  "detection_counts": {
    "likely_ai": 2,
    "likely_human": 12,
    "uncertain": 2
  },
  "total_classifications": 16,
  "verified_certificate_count": 1
}
```

This includes:

- Detection pattern: likely AI vs uncertain vs likely human
- Appeal rate
- Average confidence
- Verified certificate count

---

## Stretch Feature: Multi-Modal / Second Content Type Support

The `POST /submit-metadata` endpoint supports structured metadata as a second content type.

Instead of analyzing the writing directly, this endpoint analyzes:

- Title
- Description
- Editing time
- Revision count
- Whether the creator disclosed AI tool use

Example response:

```json
{
  "attribution": "likely_human",
  "confidence": 0.2,
  "content_id": "ecc878c4-50cb-4ca0-b415-55c341b157a0",
  "content_type": "metadata",
  "creator_id": "metadata-user-1",
  "label": "This writing shows stronger signs of being written by a person. No AI-generated label is being applied based on the current review.",
  "signals": {
    "editing_minutes": 45,
    "metadata_reasons": [
      "Longer editing time supports human revision effort.",
      "Multiple revisions support human writing effort."
    ],
    "metadata_score": 0.2,
    "revision_count": 6,
    "used_ai_tool": false
  },
  "status": "classified",
  "title": "Moving to a New City"
}
```

Metadata scoring uses simple rules:

- Very low editing time increases AI-likelihood.
- Very few revisions increases AI-likelihood.
- Longer editing time lowers AI-likelihood.
- Multiple revisions lower AI-likelihood.
- Disclosed AI tool use increases AI-likelihood but is not treated as wrongdoing.

---

## Known Limitations

### Formal human writing may be misclassified

Academic or professional writing can use polished structure, transition phrases, and formal vocabulary. The LLM and repetition signals may treat this as AI-like even if the content was written by a person.

### Short poems, captions, or fragments are difficult to classify

Stylometric analysis depends on sentence count, word count, sentence length variance, vocabulary diversity, and punctuation density. Very short content may not provide enough evidence, so the system may return a default or uncertain score.

### Non-native English writing may be unfairly flagged

Some non-native English writers use repeated phrasing, simpler vocabulary, or formal structure. Those patterns can overlap with AI-like signals. This is why the system uses a wide uncertain range and includes an appeal workflow.

### Human-edited AI text is hard to identify

If a creator uses AI and then heavily rewrites the output, the final text may look human according to stylometric signals. The system may return uncertain or likely human even if AI was involved earlier.

---

## Spec Reflection

The planning document helped because it forced the thresholds, signal weights, label text, and appeal behavior to be decided before implementation. This made it easier to compare the code against the intended design.

One important implementation divergence was the way attribution labels were handled. In an early version, the Groq response could return `likely_ai` even when the numeric score was `0.70`. My written spec said high-confidence AI should start at `0.75`, so I changed the code to use my own threshold helper for the final attribution instead of trusting the model's category text directly. This kept the implementation consistent with the spec and made the system more cautious.

Another divergence was in the multi-modal stretch feature. Instead of processing images or audio directly, I implemented structured metadata submission. This still adds a second content type, but keeps the system free, backend-focused, and explainable.

---

## AI Usage

### Instance 1: Planning and Architecture

I used an AI tool to help convert the project rubric into an implementation plan. I directed it to organize the required features into a backend architecture, detection pipeline, confidence scoring plan, transparency label plan, and appeal workflow.

What I revised:

I rewrote the architecture diagram into a clearer ASCII diagram and adjusted the design to make false positives less likely. I also added specific edge cases such as formal academic writing, short poems, and non-native English writing.

---

### Instance 2: Flask Backend Skeleton

I used an AI tool to help generate the initial Flask structure for `POST /submit` and `GET /log`. The output helped with request validation, JSON responses, and simple audit log helper functions.

What I revised:

I kept the implementation simple and beginner-friendly. I used a JSON audit log instead of a database because it is easier to inspect for grading and still satisfies the structured log requirement.

---

### Instance 3: Detection and Scoring Functions

I used an AI tool to help draft the stylometric scoring and repetition scoring functions. I directed it to use measurable text properties such as sentence length variance, vocabulary diversity, punctuation density, generic phrase hits, and repeated words.

What I revised:

I manually adjusted the weights and thresholds to match my `planning.md`. I also overrode the LLM's category label when necessary so the final attribution always follows the project's defined confidence ranges.

---

## Walkthrough Video

[Watch the Provenance Guard walkthrough video](https://www.loom.com/share/4980582d48b346a2b08fd0248653d8a6)

---

