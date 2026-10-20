"""
Tests for Day 16: FAQ-first response routing in the reply endpoint.

POST /api/v1/conversations/{session_id}/reply

Verifies that:
  - A relevant FAQ question receives the expected FAQ answer (no Gemini call).
  - An unrelated question falls back to Gemini.
  - Gemini is not called when a reliable FAQ answer is sufficient.
  - A weak or irrelevant FAQ result is not returned as an answer.
  - Gemini fallback receives the system prompt and relevant history.
  - The current message is not duplicated in history passed to Gemini.
  - Customer message and assistant response are persisted correctly.
  - The response identifies the correct answer_source.
  - Different conversations remain isolated.
  - Invalid conversation IDs are handled correctly.
  - Gemini errors are handled safely when on the Gemini path.

All Gemini API calls and FAQ searches are monkeypatched where necessary so
these tests do not require a live API key, consume real quota, or use the
network.
"""

import pytest

from app.services.prompts import FAQ_RELEVANCE_THRESHOLD, SYSTEM_PROMPT


REPLY_URL = "/api/v1/conversations/{session_id}/reply"
_GEMINI_PATCH = "app.main.generate_context_aware_reply"
_FAQ_PATCH = "app.main.faq_service_search"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_conversation(client):
    """Create a new conversation and return its session_id."""
    response = client.post("/api/v1/conversations")
    assert response.status_code == 201
    return response.json()["session_id"]


def _send_message(client, session_id: str, content: str) -> dict:
    """Post a user message to the given conversation via the plain endpoint."""
    response = client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={"message": content},
    )
    assert response.status_code == 201
    return response.json()


def _reply(client, session_id: str, message: str):
    """Call the FAQ-first reply endpoint."""
    return client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": message},
    )


# ---------------------------------------------------------------------------
# 1. FAQ hit: relevant question receives the FAQ answer, Gemini is NOT called
# ---------------------------------------------------------------------------


def test_faq_hit_returns_faq_answer(client, monkeypatch):
    """A question that scores above the threshold must return the FAQ answer."""
    gemini_called = {"called": False}

    def fake_gemini(message, history, system_prompt):
        gemini_called["called"] = True
        return "Gemini reply"

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    # "How can I track my order?" maps to FAQ001 with a very high score.
    session_id = _create_conversation(client)
    response = _reply(client, session_id, "How can I track my order?")

    assert response.status_code == 201
    data = response.json()

    # The content must be the FAQ answer, not a Gemini-invented string.
    assert "tracking" in data["content"].lower()
    assert not gemini_called["called"], "Gemini must NOT be called when a FAQ match is found"


def test_faq_hit_sets_answer_source_to_faq(client, monkeypatch):
    """answer_source must be 'faq' when the FAQ path is taken."""
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Gemini reply")

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "How can I track my order?")

    assert response.status_code == 201
    assert response.json()["answer_source"] == "faq"


def test_faq_hit_uses_highest_scoring_match(client, monkeypatch):
    """The answer returned must come from the best-matching FAQ entry."""
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Gemini reply")

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "How do I reset my password?")

    assert response.status_code == 201
    data = response.json()
    # FAQ020 answer mentions "Forgot Password" and "email address"
    assert "password" in data["content"].lower()


# ---------------------------------------------------------------------------
# 2. Gemini fallback: unrelated question bypasses FAQ and calls Gemini
# ---------------------------------------------------------------------------


def test_gemini_fallback_for_unrelated_question(client, monkeypatch):
    """A question with no FAQ match above the threshold must call Gemini."""
    gemini_called = {"called": False}

    def fake_gemini(message, history, system_prompt):
        gemini_called["called"] = True
        return "Gemini fallback reply"

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    session_id = _create_conversation(client)
    # This question has no similarity to any FAQ entry.
    response = _reply(client, session_id, "Tell me about quantum computing")

    assert response.status_code == 201
    assert gemini_called["called"], "Gemini must be called when no FAQ match is found"
    assert response.json()["content"] == "Gemini fallback reply"


def test_gemini_fallback_sets_answer_source_to_gemini(client, monkeypatch):
    """answer_source must be 'gemini' when the Gemini path is taken."""
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Gemini answer")

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Tell me about quantum computing")

    assert response.status_code == 201
    assert response.json()["answer_source"] == "gemini"


# ---------------------------------------------------------------------------
# 3. Gemini is not called when FAQ is sufficient (mock-controlled)
# ---------------------------------------------------------------------------


def test_gemini_not_called_when_faq_is_sufficient(client, monkeypatch):
    """
    With search_faqs returning a high-score hit, Gemini must never be invoked.
    This uses a mock FAQ result to control the threshold precisely.
    """
    gemini_call_count = {"n": 0}

    def fake_gemini(message, history, system_prompt):
        gemini_call_count["n"] += 1
        return "Gemini reply"

    faq_result = [
        {
            "id": "FAQ001",
            "category": "orders",
            "question": "How can I track my order?",
            "answer": "Use the tracking link in your confirmation email.",
            "score": 0.9,
        }
    ]

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: faq_result)

    session_id = _create_conversation(client)
    _reply(client, session_id, "Anything - FAQ mock controls the result")

    assert gemini_call_count["n"] == 0, (
        "Gemini must not be called when a high-score FAQ answer is available"
    )


# ---------------------------------------------------------------------------
# 4. Weak or irrelevant FAQ result does not become an incorrect answer
# ---------------------------------------------------------------------------


def test_low_score_faq_result_triggers_gemini_fallback(client, monkeypatch):
    """
    When search_faqs returns no results (score below min_score), Gemini is called.
    This verifies that the threshold gate works correctly.
    """
    gemini_called = {"called": False}

    def fake_gemini(message, history, system_prompt):
        gemini_called["called"] = True
        return "Gemini reply for low-score scenario"

    # Simulate search_faqs finding nothing above the threshold.
    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Does your company accept cryptocurrency?")

    assert response.status_code == 201
    assert gemini_called["called"], "Gemini must be called when search_faqs returns empty"


def test_threshold_constant_is_within_valid_range():
    """FAQ_RELEVANCE_THRESHOLD must be a float between 0.0 and 1.0."""
    assert isinstance(FAQ_RELEVANCE_THRESHOLD, float)
    assert 0.0 <= FAQ_RELEVANCE_THRESHOLD <= 1.0


# ---------------------------------------------------------------------------
# 5. Gemini fallback receives system prompt and history
# ---------------------------------------------------------------------------


def test_gemini_fallback_receives_system_prompt(client, monkeypatch):
    """The system_prompt argument received by Gemini must equal SYSTEM_PROMPT."""
    captured = {}

    def fake_gemini(message, history, system_prompt):
        captured["system_prompt"] = system_prompt
        return "Captured."

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Hello")

    assert response.status_code == 201
    assert captured["system_prompt"] == SYSTEM_PROMPT


def test_gemini_fallback_receives_prior_history(client, monkeypatch):
    """History passed to Gemini must include prior conversation messages."""
    captured = {}

    def fake_gemini(message, history, system_prompt):
        captured["history"] = history
        return "Got it."

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    _send_message(client, session_id, "Previous user message")
    _reply(client, session_id, "Follow-up question")

    assert len(captured["history"]) >= 1
    contents = [entry["content"] for entry in captured["history"]]
    assert "Previous user message" in contents


# ---------------------------------------------------------------------------
# 6. Current message not duplicated in history when Gemini path is taken
# ---------------------------------------------------------------------------


def test_current_message_not_in_gemini_history(client, monkeypatch):
    """The message forwarded to the reply endpoint must not appear in history."""
    captured = {}

    def fake_gemini(message, history, system_prompt):
        captured["message"] = message
        captured["history"] = history
        return "OK."

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
    # Force Gemini path regardless of query content.
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    current = "My totally unique question 12345xyzzy"
    _reply(client, session_id, current)

    assert captured["message"] == current
    for entry in captured.get("history", []):
        assert entry["content"] != current


# ---------------------------------------------------------------------------
# 7. Persistence: customer message and assistant response are saved
# ---------------------------------------------------------------------------


def test_faq_reply_persists_both_messages(client, monkeypatch):
    """Both user and assistant messages must be saved when FAQ path is taken."""
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Gemini reply")

    session_id = _create_conversation(client)
    _reply(client, session_id, "How can I track my order?")

    history = client.get(
        f"/api/v1/conversations/{session_id}/messages"
    ).json()

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "How can I track my order?"
    assert history[1]["role"] == "assistant"
    # Content must be non-empty and not equal to Gemini mock (FAQ was used).
    assert history[1]["content"]
    assert history[1]["content"] != "Gemini reply"


def test_gemini_reply_persists_both_messages(client, monkeypatch):
    """Both user and assistant messages must be saved when Gemini path is taken."""
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Persisted Gemini answer")
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    _reply(client, session_id, "Does not match any FAQ entry")

    history = client.get(
        f"/api/v1/conversations/{session_id}/messages"
    ).json()

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Persisted Gemini answer"


# ---------------------------------------------------------------------------
# 8. Response shape: answer_source field is present and valid
# ---------------------------------------------------------------------------


def test_reply_response_includes_answer_source_field(client, monkeypatch):
    """The reply response must include the answer_source field."""
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Gemini answer")
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Hello there")

    assert response.status_code == 201
    data = response.json()
    assert "answer_source" in data
    assert data["answer_source"] in ("faq", "gemini")


def test_reply_response_has_all_required_fields(client, monkeypatch):
    """The reply response must include all MessageResponse fields plus answer_source."""
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Shape test reply")
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Shape test question")

    assert response.status_code == 201
    data = response.json()

    assert data["role"] == "assistant"
    assert data["content"] == "Shape test reply"
    assert "id" in data
    assert "conversation_id" in data
    assert "created_at" in data
    assert "answer_source" in data


# ---------------------------------------------------------------------------
# 9. Conversation isolation
# ---------------------------------------------------------------------------


def test_faq_routing_is_isolated_per_conversation(client, monkeypatch):
    """FAQ and Gemini responses in separate conversations must not cross-contaminate."""
    call_log = []

    def fake_gemini(message, history, system_prompt):
        call_log.append({"message": message, "history": history})
        return "Gemini reply for conversation B"

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    session_a = _create_conversation(client)
    session_b = _create_conversation(client)

    # Conversation A: FAQ match - no Gemini call.
    faq_result = [
        {
            "id": "FAQ001",
            "category": "orders",
            "question": "How can I track my order?",
            "answer": "Use the tracking link.",
            "score": 0.9,
        }
    ]
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: faq_result)
    _reply(client, session_a, "Track my order")

    # Conversation B: no FAQ match - Gemini called.
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])
    _reply(client, session_b, "Unrelated query xyz")

    # Gemini was called once (for B only).
    assert len(call_log) == 1

    # History for B must not contain A's messages.
    history_b_contents = [e["content"] for e in call_log[0]["history"]]
    assert "Track my order" not in history_b_contents


# ---------------------------------------------------------------------------
# 10. Invalid conversation ID handling
# ---------------------------------------------------------------------------


def test_faq_reply_returns_404_for_unknown_session(client, monkeypatch):
    """An unknown session_id must return 404 before any FAQ or Gemini call."""
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    response = _reply(client, "totally-invalid-session-id", "Hello")

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


# ---------------------------------------------------------------------------
# 11. Gemini error handling on the Gemini path
# ---------------------------------------------------------------------------


def test_gemini_error_returns_502(client, monkeypatch):
    """A Gemini RuntimeError on the Gemini path must return 502."""

    def fake_gemini(message, history, system_prompt):
        raise RuntimeError("Gemini is temporarily unavailable.")

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Unknown query xyz")

    assert response.status_code == 502
    assert "Gemini" in response.json()["detail"]


def test_missing_api_key_returns_500(client, monkeypatch):
    """A missing-API-key RuntimeError on the Gemini path must return 500."""

    def fake_gemini(message, history, system_prompt):
        raise RuntimeError("GEMINI_API_KEY is missing from the .env file.")

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Unknown query xyz")

    assert response.status_code == 500
    assert "not configured" in response.json()["detail"].lower()


def test_gemini_error_does_not_expose_internals(client, monkeypatch):
    """Gemini error responses must not leak raw exception messages or stack traces."""

    def fake_gemini(message, history, system_prompt):
        raise RuntimeError("Secret internal error XYZ-999")

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Unknown query xyz")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Secret internal error" not in detail
    assert "XYZ-999" not in detail

