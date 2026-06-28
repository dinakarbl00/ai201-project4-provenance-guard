import json
import urllib.request
import urllib.error


BASE_URL = "http://127.0.0.1:5000"


def post_json(endpoint, data):
    url = BASE_URL + endpoint
    body = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request) as response:
            response_body = response.read().decode("utf-8")
            return response.status, json.loads(response_body)

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")

        try:
            parsed_error = json.loads(error_body)
        except json.JSONDecodeError:
            parsed_error = {"error": error_body}

        return error.code, parsed_error


def get_json(endpoint):
    url = BASE_URL + endpoint

    try:
        with urllib.request.urlopen(url) as response:
            response_body = response.read().decode("utf-8")
            return response.status, json.loads(response_body)

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")

        try:
            parsed_error = json.loads(error_body)
        except json.JSONDecodeError:
            parsed_error = {"error": error_body}

        return error.code, parsed_error


def print_result(title, status, result):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print(f"Status Code: {status}")
    print(json.dumps(result, indent=4))


def main():
    saved_ids = {}

    status, result = get_json("/")
    print_result("1. Health Check", status, result)

    strong_ai_text = (
        "It is important to note that artificial intelligence plays a crucial role "
        "in modern society. Furthermore, artificial intelligence plays a crucial role "
        "in business innovation. Overall, artificial intelligence plays a crucial role "
        "in responsible deployment. In conclusion, artificial intelligence plays a "
        "crucial role across various sectors."
    )

    status, result = post_json("/submit", {
        "text": strong_ai_text,
        "creator_id": "video-strong-ai"
    })
    print_result("2. High-Confidence AI Text Submission", status, result)
    saved_ids["strong_ai_content_id"] = result.get("content_id")

    human_text = (
        "ok so i finally tried that new ramen place downtown and honestly? "
        "underwhelming. the broth was fine but they put WAY too much sodium in it "
        "and i was thirsty for like three hours after. my friend got the spicy "
        "version and said it was better. probably won't go back unless someone "
        "drags me there"
    )

    status, result = post_json("/submit", {
        "text": human_text,
        "creator_id": "video-human"
    })
    print_result("3. Human-Like Text Submission", status, result)
    saved_ids["human_content_id"] = result.get("content_id")

    uncertain_text = (
        "Artificial intelligence represents a transformative paradigm shift in modern society. "
        "It is important to note that while the benefits of AI are numerous, it is equally "
        "essential to consider the ethical implications. Furthermore, stakeholders across "
        "various sectors must collaborate to ensure responsible deployment."
    )

    status, result = post_json("/submit", {
        "text": uncertain_text,
        "creator_id": "video-uncertain"
    })
    print_result("4. Lower-Confidence / Uncertain Text Submission", status, result)
    saved_ids["uncertain_content_id"] = result.get("content_id")

    status, result = post_json("/appeal", {
        "content_id": saved_ids["uncertain_content_id"],
        "creator_reasoning": (
            "I wrote this myself and the topic is formal, so the writing may sound polished. "
            "I want a human reviewer to check the decision."
        )
    })
    print_result("5. Appeals Workflow", status, result)

    status, result = post_json("/verify-human", {
        "content_id": saved_ids["human_content_id"],
        "creator_id": "video-human",
        "verification_statement": (
            "I wrote this myself from a personal restaurant experience and can explain my drafting process."
        )
    })
    print_result("6. Provenance Certificate", status, result)

    status, result = post_json("/submit-metadata", {
        "creator_id": "video-metadata-user",
        "title": "Moving to a New City",
        "description": "A short poem about adjusting to a new city and missing home.",
        "editing_minutes": 45,
        "revision_count": 6,
        "used_ai_tool": False
    })
    print_result("7. Metadata Submission", status, result)

    status, result = get_json("/analytics")
    print_result("8. Analytics Dashboard", status, result)

    status, result = get_json("/log")
    entries = result.get("entries", [])

    short_log = {
        "count": result.get("count"),
        "latest_entries": entries[-6:]
    }

    print_result("9. Audit Log Latest Entries", status, short_log)

    print("\n" + "=" * 80)
    print("10. Rate Limit Demo")
    print("=" * 80)

    rate_body = {
        "text": "This is a test submission for rate limit testing purposes only.",
        "creator_id": "video-ratelimit-test"
    }

    for i in range(1, 13):
        status, result = post_json("/submit", rate_body)
        print(f"Rate Limit Request {i} -> Status Code: {status}")


if __name__ == "__main__":
    main()