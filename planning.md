# Provenance Guard Planning

## Project Goal

Provenance Guard is a backend system for a creative writing platform. It accepts submitted text, analyzes whether the writing appears AI-generated, human-written, or uncertain, returns a confidence score, shows a plain-language transparency label, stores a structured audit log, and allows creators to appeal a classification.

The goal is not to perfectly detect AI writing. AI detection is imperfect, so this system should communicate uncertainty clearly and give creators a fair appeal process.

---

## Architecture

```text
                         ┌──────────────────────────────┐
                         │          Client / User       │
                         │  Creative writing platform   │
                         └───────────────┬──────────────┘
                                         │
                                         │ POST /submit
                                         │ { text, creator_id }
                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                              Flask API                              │
│                                                                     │
│  Validates request, creates content_id, and sends text to pipeline  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ raw submitted text
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                       Multi-Signal Detection Pipeline              │
│                                                                    │
│   ┌──────────────────────┐   ┌──────────────────────┐              │
│   │ Signal 1             │   │ Signal 2             │              │
│   │ Groq LLM score       │   │ Stylometric score    │              │
│   │ Meaning/style check  │   │ Structure check      │              │
│   └──────────┬───────────┘   └──────────┬───────────┘              │
│              │                          │                          │
│              │                          │                          │
│              ▼                          ▼                          │
│          llm_score              stylometric_score                  │
│                                                                    │
│   ┌──────────────────────┐                                         │
│   │ Signal 3             │                                         │
│   │ Repetition / generic │                                         │
│   │ phrase score         │                                         │
│   └──────────┬───────────┘                                         │
│              │                                                     │
│              ▼                                                     │
│        repetition_score                                            │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                │ individual signal scores
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Confidence Scoring                          │
│                                                                     │
│ combined_ai_score = 50% LLM + 35% stylometric + 15% repetition      │
│                                                                     │
│ 0.00 - 0.44  → likely_human                                         │
│ 0.45 - 0.74  → uncertain                                            │
│ 0.75 - 1.00  → likely_ai                                            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ attribution + confidence
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Transparency Label Generator                    │
│                                                                     │
│ Converts the score into plain-language label text for readers       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ final result
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                            Audit Log                                 │
│                                                                      │
│ Stores timestamp, content_id, attribution, confidence, signal scores,│
│ label text, and status in structured JSON                            │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                │ JSON response
                                ▼
                         ┌───────────────────────────────┐
                         │        API Response           │
                         │ content_id                    │
                         │ attribution                   │
                         │ confidence                    │
                         │ label                         │
                         │ signal scores                 │
                         │ status                        │
                         └───────────────────────────────┘



                         ┌───────────────────────────────┐
                         │           Creator             │
                         │ Disagrees with classification │
                         └───────────────┬───────────────┘
                                         │
                                         │ POST /appeal
                                         │ { content_id, creator_reasoning }
                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                              Flask API                              │
│                                                                     │
│ Finds the original content decision using content_id                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ original classification found
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Status Update Layer                         │
│                                                                     │
│ Changes content status from "classified" to "under_review"          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                │ appeal details
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                            Audit Log                                 │
│                                                                      │
│ Adds appeal entry with timestamp, creator reasoning, original result,│
│ original confidence score, and updated status                        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                │ confirmation response
                                ▼
                         ┌──────────────────────────────┐
                         │        API Response          │
                         │ status: under_review         │
                         │ message: appeal received     │
                         └──────────────────────────────┘
```

When a creator submits text, the API sends the text through three detection signals. Each signal produces an AI-likelihood score from 0 to 1. The scoring layer combines these scores into one confidence score, maps that score to an attribution result, generates a reader-friendly transparency label, saves the result in the audit log, and returns a structured JSON response.

When a creator appeals, the system records their reasoning, changes the content status to `under_review`, and adds the appeal to the audit log alongside the original classification.

---

## API Surface

### POST /submit

Accepts a text submission for attribution analysis.

Request body:

```json
{
  "text": "Submitted writing goes here.",
  "creator_id": "creator-123"
}
```

Response body:

```json
{
  "content_id": "unique-content-id",
  "creator_id": "creator-123",
  "attribution": "likely_ai | uncertain | likely_human",
  "confidence": 0.82,
  "label": "Plain-language transparency label",
  "signals": {
    "llm_score": 0.85,
    "stylometric_score": 0.78,
    "repetition_score": 0.62
  },
  "status": "classified"
}
```

### POST /appeal

Accepts a creator appeal for a previous classification.

Request body:

```json
{
  "content_id": "unique-content-id",
  "creator_reasoning": "I wrote this myself and can explain my process."
}
```

Response body:

```json
{
  "content_id": "unique-content-id",
  "status": "under_review",
  "message": "Appeal received. This content is now under review."
}
```

### GET /log

Returns recent structured audit log entries.

### GET /analytics

Returns simple dashboard metrics for the analytics stretch feature.

### POST /verify-human

Creates a provenance certificate after a creator completes a verification step.

### POST /submit-metadata

Processes structured metadata as the second content type for the multi-modal stretch feature.

---

## Detection Signals

The system will use three detection signals. This gives the project an ensemble detection pipeline instead of relying on only one method.

### Signal 1: Groq LLM Classification Score

This signal asks a Groq-hosted LLM to judge whether the text appears AI-generated or human-written.

What it measures:

* Overall semantic and stylistic AI-likeness
* Whether the writing feels overly polished, generic, repetitive, or formulaic
* Whether the wording resembles common AI-generated explanations

Output:

```text
llm_score: float from 0.0 to 1.0
```

A higher score means the LLM believes the text is more likely AI-generated.

Why I chose it:

The LLM can notice broad writing patterns that are hard to capture with simple rules, such as generic structure, overly balanced phrasing, and lack of personal specificity.

What it misses:

The LLM can misclassify formal human writing as AI-generated. It can also miss AI text that has been heavily edited by a human. Because of this, the LLM signal should not be the only signal used.

---

### Signal 2: Stylometric Heuristic Score

This signal uses simple Python calculations to measure structural properties of the text.

Metrics used:

* Sentence length variance
* Vocabulary diversity using type-token ratio
* Punctuation density

What it measures:

Stylometry measures the shape of the writing rather than the meaning. Human writing often has more uneven sentence lengths, more irregular punctuation, and more personal variation. AI writing is often smoother and more uniform.

Output:

```text
stylometric_score: float from 0.0 to 1.0
```

A higher score means the text structurally looks more AI-like.

Why I chose it:

This signal is independent from the LLM. It does not ask another model for an opinion. It looks at measurable properties of the submitted text.

What it misses:

Short text is difficult to judge with stylometry because there may not be enough sentences or words. Poems, academic writing, and non-native English writing may also look unusually structured and could be scored incorrectly.

---

### Signal 3: Repetition and Generic Phrase Score

This signal checks for repeated language patterns and common generic phrases that appear often in AI-generated writing.

Examples of phrases checked:

* "It is important to note"
* "Furthermore"
* "In conclusion"
* "Overall"
* "plays a crucial role"
* "transformative"
* "various sectors"

What it measures:

This signal measures whether the text relies on repeated transitions, broad filler phrases, or generic wording that does not add much specific detail.

Output:

```text
repetition_score: float from 0.0 to 1.0
```

A higher score means the text contains more generic or repetitive AI-like phrasing.

Why I chose it:

This signal is simple, explainable, and easy to show in the API response. It also helps catch polished AI text that repeatedly uses safe, generic transitions.

What it misses:

Some human academic or professional writing naturally uses transition phrases. Also, AI text that avoids these phrases may receive a low repetition score.

---

## Ensemble Scoring Strategy

The final AI-likelihood score will combine the three signals with weights.

```text
combined_ai_score =
  (0.50 * llm_score)
+ (0.35 * stylometric_score)
+ (0.15 * repetition_score)
```

Reasoning:

* The LLM score gets the highest weight because it captures the broadest judgment.
* The stylometric score gets a strong weight because it is independent and measurable.
* The repetition score gets a smaller weight because it is useful but easier to fool.

Conflict handling:

If the LLM score is high but the stylometric score is low, the final score should usually land in the uncertain range instead of automatically labeling the text as AI-generated. This helps reduce false positives against human writers.

---

## Uncertainty Representation

The system will treat confidence as an AI-likelihood score from 0.0 to 1.0.

```text
0.00 - 0.44 = likely human-written
0.45 - 0.74 = uncertain
0.75 - 1.00 = likely AI-generated
```

A score near 0.50 means the system does not have enough evidence to make a strong claim. A score near 0.95 means the signals strongly agree that the text appears AI-generated. A score near 0.15 means the signals strongly suggest human writing.

The uncertain range is intentionally wide because false positives are harmful on a writing platform. Labeling a real creator's work as AI-generated could damage trust, so the system should avoid strong accusations unless multiple signals agree.

---

## Transparency Label Design

The API will return one of these exact label texts.

| Result type                |      Score range | Exact label text                                                                                                                                                    |
| -------------------------- | ---------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| High-confidence AI         |      0.75 - 1.00 | "This writing shows strong signs of being AI-generated. The platform is showing this label so readers have more context, but the creator may appeal this decision." |
| Uncertain                  |      0.45 - 0.74 | "We are not sure whether this writing was AI-generated or human-written. The available signals are mixed, so readers should treat this label as uncertain."         |
| High-confidence human      |      0.00 - 0.44 | "This writing shows stronger signs of being written by a person. No AI-generated label is being applied based on the current review."                               |
| Verified human certificate | verified creator | "Verified human-created work: the creator completed an additional verification step for this submission."                                                           |

These labels use plain language and avoid technical phrases such as classifier, logits, model output, or probability distribution.

---

## Appeals Workflow

A creator can submit an appeal when they believe their content was misclassified.

The appeal request must include:

* `content_id`
* `creator_reasoning`

When an appeal is received, the system will:

1. Find the original content classification.
2. Update the content status from `classified` to `under_review`.
3. Add the creator's reasoning to the audit log.
4. Return a confirmation response.

The system will not automatically reclassify the content after an appeal. A human reviewer would need to inspect the original text, signal scores, label, and creator reasoning.

A reviewer should see:

* Content ID
* Creator ID
* Original attribution result
* Original confidence score
* Individual signal scores
* Original timestamp
* Appeal timestamp
* Creator reasoning
* Current status: `under_review`

---

## Rate Limiting Plan

The `/submit` endpoint will use this limit:

```text
10 requests per minute
100 requests per day
```

Reasoning:

A normal writer on a creative platform may test a few drafts in a short time, so 10 submissions per minute is enough for realistic use. A daily limit of 100 submissions is high enough for normal writing behavior but low enough to reduce abuse from scripts trying to flood the system.

The `/appeal` endpoint does not need the same strict limit because appeals require a real content ID and are less likely to be spammed during normal use.

---

## Audit Log Plan

The audit log will be stored as structured JSON in:

```text
data/audit_log.json
```

Each classification entry will include:

```json
{
  "event_type": "classification",
  "content_id": "unique-content-id",
  "creator_id": "creator-123",
  "timestamp": "2026-06-27T12:00:00Z",
  "attribution": "likely_ai",
  "confidence": 0.82,
  "signals": {
    "llm_score": 0.85,
    "stylometric_score": 0.78,
    "repetition_score": 0.62
  },
  "label": "Transparency label text",
  "status": "classified"
}
```

Each appeal entry will include:

```json
{
  "event_type": "appeal",
  "content_id": "unique-content-id",
  "creator_id": "creator-123",
  "timestamp": "2026-06-27T12:10:00Z",
  "status": "under_review",
  "appeal_reasoning": "Creator explanation goes here.",
  "original_attribution": "likely_ai",
  "original_confidence": 0.82
}
```

The `GET /log` endpoint will return these entries so they can be shown in the README and walkthrough.

---

## Stretch Feature Plan

### Stretch 1: Ensemble Detection

The system will use three distinct signals: Groq LLM score, stylometric heuristic score, and repetition/generic phrase score. The final score will use weighted scoring. If signals disagree, the combined score should move toward the uncertain range instead of forcing a strong result.

### Stretch 2: Provenance Certificate

The system will include a `POST /verify-human` endpoint. A creator can complete a simple verification step by submitting a short statement about their writing process.

Example request:

```json
{
  "content_id": "unique-content-id",
  "creator_id": "creator-123",
  "verification_statement": "I wrote this draft myself and can describe my writing process."
}
```

If the required fields are present, the content receives a verified human certificate label:

```text
"Verified human-created work: the creator completed an additional verification step for this submission."
```

This verified label must be visibly different from the standard transparency labels.

### Stretch 3: Analytics Dashboard

The system will include a `GET /analytics` endpoint that returns at least three metrics:

* AI vs human vs uncertain detection counts
* Appeal rate
* Average confidence score
* Verified certificate count

This gives a simple dashboard-style view of detection patterns.

### Stretch 4: Multi-Modal Support

The system will include a `POST /submit-metadata` endpoint for structured metadata. Instead of analyzing the full creative text, this endpoint analyzes metadata such as title, description, editing time, revision count, and tool disclosure.

Example request:

```json
{
  "creator_id": "creator-123",
  "title": "My Poem",
  "description": "A poem about moving to a new city.",
  "editing_minutes": 45,
  "revision_count": 6,
  "used_ai_tool": false
}
```

Signals for metadata:

* Very low editing time with very polished description may increase AI-likelihood.
* Higher revision count may support human authorship.
* Explicit AI tool disclosure increases AI-likelihood but should not be treated as wrongdoing.

This is not true image/audio analysis, but it is a second content type because the pipeline processes structured metadata instead of normal text.

---

## Anticipated Edge Cases

### Edge Case 1: Formal human academic writing

A student or professional may write in a polished, structured style with transition phrases and balanced sentences. The stylometric and repetition signals may score this as AI-like even when it is human-written.

How the system handles it:

The uncertain range is wide, and appeals are supported. If the signals do not strongly agree, the system should avoid a high-confidence AI label.

### Edge Case 2: Short submissions

A short poem, caption, or paragraph may not contain enough text for reliable sentence variance or vocabulary diversity. Stylometric scores may be unstable.

How the system handles it:

Short texts should usually produce more moderate scores. The README will document that very short content is a known limitation.

### Edge Case 3: Non-native English writing

A non-native English speaker may write in a formal or repetitive style. This could be incorrectly interpreted as AI-like.

How the system handles it:

The label avoids accusing the creator, and the appeal workflow lets the creator explain their writing context.

### Edge Case 4: Human-edited AI text

A creator may generate text with AI and heavily edit it. The final writing may look human in stylometric signals but still have some AI-like semantic patterns.

How the system handles it:

The ensemble can show mixed evidence and return an uncertain label.

---

## AI Tool Plan

### M3: Submission Endpoint + First Signal

Spec sections to provide to AI:

* Architecture
* API Surface
* Signal 1: Groq LLM Classification Score
* Audit Log Plan

Prompt goal:

Ask the AI tool to generate a simple Flask app skeleton, a `POST /submit` route, and a Groq LLM signal function that returns a score from 0 to 1.

What I will verify:

* The `/submit` route accepts `text` and `creator_id`.
* The response includes `content_id`, `attribution`, `confidence`, `label`, and `status`.
* The Groq function returns structured data, not unformatted text.
* A submission creates a structured audit log entry.

What I will revise or override:

I will keep the code simple and avoid unnecessary classes or complex abstractions. If the AI generates too much code, I will reduce it to a readable beginner-friendly version.

---

### M4: Second and Third Signals + Confidence Scoring

Spec sections to provide to AI:

* Detection Signals
* Ensemble Scoring Strategy
* Uncertainty Representation
* Architecture

Prompt goal:

Ask the AI tool to generate simple Python functions for stylometric scoring, repetition scoring, and weighted confidence scoring.

What I will verify:

* Clearly AI-like text receives a higher score.
* Casual human-like text receives a lower score.
* Borderline examples land closer to the uncertain range.
* The audit log records all individual signal scores.

What I will revise or override:

I will manually adjust thresholds if the scores are too extreme or if too many examples get classified as high-confidence AI.

---

### M5: Production Layer

Spec sections to provide to AI:

* Transparency Label Design
* Appeals Workflow
* Rate Limiting Plan
* Audit Log Plan
* Stretch Feature Plan

Prompt goal:

Ask the AI tool to generate a label mapping function, a `POST /appeal` endpoint, rate limiting setup, and simple stretch endpoints for analytics, provenance certificate, and metadata submission.

What I will verify:

* All three standard label variants are reachable.
* Appeals update status to `under_review`.
* The appeal appears in the audit log.
* Rate limiting returns a 429 response after the limit is exceeded.
* Analytics returns at least three metrics.
* Verified content receives a visibly different label.
* Metadata submissions return attribution, confidence, and label.

What I will revise or override:

I will make the label text match this planning document exactly. If the AI changes the wording, I will restore my planned wording so the README, planning document, and source code stay consistent.

---

## Validation Plan

I will test at least four text examples:

### Clearly AI-like

```text
Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.
```

Expected result:

High AI-likelihood or upper uncertain range.

### Clearly human-like

```text
ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there
```

Expected result:

Likely human-written.

### Borderline formal human writing

```text
The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations.
```

Expected result:

Uncertain.

### Borderline edited AI-like writing

```text
I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type.
```

Expected result:

Uncertain or moderate AI-likelihood.

I will use these examples to confirm that confidence scores vary meaningfully instead of producing the same result for every input.
