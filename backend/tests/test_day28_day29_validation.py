"""
Tests for Day 28 & Day 29: Security, Performance, Reliability and Final Regression Validation.

Covers:
  1. Input validation & boundary testing across all endpoints (empty/whitespace, max length, malformed types).
  2. Session ID security, length constraints, and malformed parameter handling (HTTP 404).
  3. Safe error handling (Gemini failures, missing API keys, database rollback, internal exception masking).
  4. End-to-end user scenarios:
     - Scenario 1: FAQ-first routing and Gemini bypass.
     - Scenario 2: Gemini fallback with grounded context.
     - Scenario 3: Multi-turn history limit (HISTORY_LIMIT=10), chronological ordering, and session isolation.
     - Scenario 4: Error resilience and multi-turn recovery.
"""

from unittest.mock import MagicMock
import pytest

from app.services.prompts import HISTORY_LIMIT, SYSTEM_PROMPT


REPLY_URL = "/api/v1/conversations/{session_id}/reply"
MESSAGES_URL = "/api/v1/conversations/{session_id}/messages"
_GEMINI_PATCH = "app.main.generate_context_aware_reply"
_FAQ_PATCH = "app.main.faq_service_search"


def _create_session(client) -> str:
    """Helper to create a fresh conversation session."""
    response = client.post("/api/v1/conversations")
    assert response.status_code == 201
    return response.json()["session_id"]


# ===========================================================================
# 1. Input Validation & Boundary Testing Across All Endpoints
# ===========================================================================


@pytest.mark.parametrize("blank_input", ["", "   ", "\t\t", "\n\n  \n"])
def test_empty_and_whitespace_messages_rejected_across_endpoints(client, blank_input):
    """Whitespace and empty strings must be rejected with 422 across all message-accepting endpoints."""
    session_id = _create_session(client)

    # 1. Message validation endpoint
    r1 = client.post("/api/v1/validate-message", json={"message": blank_input})
    assert r1.status_code == 422

    # 2. Conversation messages endpoint
    r2 = client.post(MESSAGES_URL.format(session_id=session_id), json={"message": blank_input})
    assert r2.status_code == 422

    # 3. Conversation reply endpoint
    r3 = client.post(REPLY_URL.format(session_id=session_id), json={"message": blank_input})
    assert r3.status_code == 422

    # 4. Direct AI reply endpoint
    r4 = client.post("/ai/reply", json={"message": blank_input})
    assert r4.status_code == 422

    # 5. FAQ search endpoint
    r5 = client.post("/api/v1/faqs/search", json={"query": blank_input})
    assert r5.status_code == 422

    # 6. NLP intent endpoint
    r6 = client.post("/api/v1/nlp/intent", json={"message": blank_input})
    assert r6.status_code == 422

    # 7. NLP entities endpoint
    r7 = client.post("/api/v1/nlp/entities", json={"message": blank_input})
    assert r7.status_code == 422

    # 8. NLP analyze endpoint
    r8 = client.post("/api/v1/nlp/analyze", json={"message": blank_input})
    assert r8.status_code == 422


def test_oversized_inputs_rejected_at_schema_boundary(client):
    """Payloads exceeding maximum boundary limits must be rejected with 422."""
    session_id = _create_session(client)

    # Messages > 2000 chars on 2000-char max endpoints
    over_2000 = "x" * 2001
    assert client.post("/api/v1/validate-message", json={"message": over_2000}).status_code == 422
    assert client.post(MESSAGES_URL.format(session_id=session_id), json={"message": over_2000}).status_code == 422
    assert client.post(REPLY_URL.format(session_id=session_id), json={"message": over_2000}).status_code == 422
    assert client.post("/api/v1/nlp/intent", json={"message": over_2000}).status_code == 422
    assert client.post("/api/v1/nlp/entities", json={"message": over_2000}).status_code == 422
    assert client.post("/api/v1/nlp/analyze", json={"message": over_2000}).status_code == 422

    # FAQ search query > 500 chars
    over_500 = "y" * 501
    assert client.post("/api/v1/faqs/search", json={"query": over_500}).status_code == 422

    # AI reply > 4000 chars
    over_4000 = "z" * 4001
    assert client.post("/ai/reply", json={"message": over_4000}).status_code == 422


@pytest.mark.parametrize("invalid_limit", [0, -1, 11, 100])
def test_faq_search_limit_boundaries_enforced(client, invalid_limit):
    """FAQ search limits outside the 1..10 range must return 422 Unprocessable Entity."""
    response = client.post(
        "/api/v1/faqs/search",
        json={"query": "order status", "limit": invalid_limit},
    )
    assert response.status_code == 422


# ===========================================================================
# 2. Session ID Security & Parameter Robustness
# ===========================================================================


@pytest.mark.parametrize("malformed_session_id", [
    "   ",
    "x" * 105,
    "non-existent-session-id-12345",
    "'; DROP TABLE conversations; --",
    "undefined",
    "null",
])
def test_malformed_and_oversized_session_ids_return_404(client, malformed_session_id):
    """Malformed, oversized, or non-existent session IDs must return 404 without crashing."""
    # 1. Post message
    r1 = client.post(
        MESSAGES_URL.format(session_id=malformed_session_id),
        json={"message": "Valid test message"},
    )
    assert r1.status_code == 404
    assert r1.json()["detail"] in ("Conversation not found", "Not Found")

    # 2. Get messages history
    r2 = client.get(MESSAGES_URL.format(session_id=malformed_session_id))
    assert r2.status_code == 404
    assert r2.json()["detail"] in ("Conversation not found", "Not Found")

    # 3. Post reply
    r3 = client.post(
        REPLY_URL.format(session_id=malformed_session_id),
        json={"message": "Valid test message"},
    )
    assert r3.status_code == 404
    assert r3.json()["detail"] in ("Conversation not found", "Not Found")


# ===========================================================================
# 3. Error Handling & Safe Responses
# ===========================================================================


def test_database_error_on_get_messages_returns_500(client, monkeypatch):
    """Database query failure during message history retrieval returns HTTP 500 cleanly."""
    session_id = _create_session(client)

    def _failing_scalars(*args, **kwargs):
        raise RuntimeError("Disk I/O error simulated")

    monkeypatch.setattr("sqlalchemy.orm.Session.scalars", _failing_scalars)

    response = client.get(MESSAGES_URL.format(session_id=session_id))
    assert response.status_code == 500
    assert "Database error while retrieving conversation messages." in response.json()["detail"]


def test_database_error_on_conversation_creation_returns_500(client, monkeypatch):
    """Database commit failure during conversation creation returns HTTP 500 cleanly."""
    def _failing_commit(*args, **kwargs):
        raise RuntimeError("Simulated DB commit error")

    monkeypatch.setattr("sqlalchemy.orm.Session.commit", _failing_commit)

    response = client.post("/api/v1/conversations")
    assert response.status_code == 500
    assert "Database error while creating conversation." in response.json()["detail"]


def test_gemini_generic_exception_normalized_to_502(client, monkeypatch):
    """Non-RuntimeError exceptions from Gemini API wrapper are safely mapped to HTTP 502."""
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    def _unexpected_gemini(*args, **kwargs):
        raise ValueError("Unexpected network disconnect occurred")

    monkeypatch.setattr(_GEMINI_PATCH, _unexpected_gemini)

    session_id = _create_session(client)
    response = client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": "Query triggering unexpected error"},
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "Gemini could not generate a response. Please try again."
    # Ensure raw exception message is not leaked
    assert "Unexpected network disconnect" not in response.json()["detail"]


# ===========================================================================
# 4. End-to-End Reliability Scenarios
# ===========================================================================


def test_scenario1_faq_response_flow(client, monkeypatch):
    """
    Scenario 1: FAQ Response
    - NLP preprocessing runs.
    - FAQ search runs first.
    - Verified FAQ answer returned.
    - Gemini is NOT called.
    - Persisted to SQLite.
    """
    gemini_called = {"called": False}

    def _spy_gemini(*args, **kwargs):
        gemini_called["called"] = True
        return "Should not be called"

    monkeypatch.setattr(_GEMINI_PATCH, _spy_gemini)

    session_id = _create_session(client)
    # "Where is my package?" is an exact match for FAQ008
    response = client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": "Where is my package?"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["answer_source"] == "faq"
    assert "package" in data["content"].lower() or "support" in data["content"].lower()
    assert not gemini_called["called"]

    # Verify both user and assistant messages exist in database
    history = client.get(MESSAGES_URL.format(session_id=session_id)).json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == data["content"]


def test_scenario2_gemini_fallback_with_business_context(client, monkeypatch):
    """
    Scenario 2: Gemini Fallback
    - Unmatched question falls back to Gemini.
    - Grounded business facts (order ORD-12345) injected.
    - Response saved correctly.
    """
    captured = {}

    def _fake_gemini(message, history, prompt):
        captured["prompt"] = prompt
        captured["message"] = message
        return "Your order ORD-12345 is currently in transit."

    monkeypatch.setattr(_GEMINI_PATCH, _fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_session(client)
    response = client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": "Check status of order ORD-12345 please."},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["answer_source"] == "gemini"
    assert "ORD-12345" in data["entities"]["order_ids"]
    assert "ORD-12345" in captured["prompt"]

    history = client.get(MESSAGES_URL.format(session_id=session_id)).json()
    assert len(history) == 2
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Your order ORD-12345 is currently in transit."


def test_scenario3_multi_turn_history_limit_and_chronology(client, monkeypatch):
    """
    Scenario 3: Multi-Turn Conversation
    - History limit (10) enforced.
    - Chronological order preserved (oldest first).
    - Current message excluded from history.
    """
    recorded_histories = []

    def _fake_gemini(message, history, prompt):
        recorded_histories.append(list(history))
        return f"Ack for {message}"

    monkeypatch.setattr(_GEMINI_PATCH, _fake_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_session(client)

    # Send 7 turns (14 messages total: 7 user + 7 assistant)
    for i in range(1, 8):
        resp = client.post(
            REPLY_URL.format(session_id=session_id),
            json={"message": f"Message turn {i}"},
        )
        assert resp.status_code == 201

    # On turn 7, there are 12 prior messages in DB (6 user + 6 assistant).
    # Since HISTORY_LIMIT = 10, Gemini must receive exactly 10 messages.
    last_history = recorded_histories[-1]
    assert len(last_history) == HISTORY_LIMIT

    # Verify chronological ordering:
    # Older messages should appear before newer ones in the history list
    first_hist_msg = last_history[0]["content"]
    last_hist_msg = last_history[-1]["content"]
    assert "turn 2" in first_hist_msg or "Ack for Message turn 1" in first_hist_msg
    assert "turn 6" in last_hist_msg or "Ack for Message turn 6" in last_hist_msg

    # Verify current turn (Message turn 7) is NOT in the history
    for entry in last_history:
        assert entry["content"] != "Message turn 7"


def test_scenario4_error_resilience_and_turn_recovery(client, monkeypatch):
    """
    Scenario 4: Error and Recovery
    - Valid turn works.
    - Invalid turn fails without breaking session.
    - Recoverable API failure doesn't corrupt state.
    - Next valid turn succeeds smoothly.
    """
    turn_count = {"calls": 0}

    def _recovering_gemini(message, history, prompt):
        turn_count["calls"] += 1
        if turn_count["calls"] == 2:
            raise RuntimeError("Temporary Gemini timeout")
        return f"Recovered reply {turn_count['calls']}"

    monkeypatch.setattr(_GEMINI_PATCH, _recovering_gemini)
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    session_id = _create_session(client)

    # Turn 1: Normal success
    r1 = client.post(REPLY_URL.format(session_id=session_id), json={"message": "First query"})
    assert r1.status_code == 201
    assert r1.json()["content"] == "Recovered reply 1"

    # Turn 2: Invalid input (whitespace) -> 422 rejected cleanly
    r2 = client.post(REPLY_URL.format(session_id=session_id), json={"message": "   "})
    assert r2.status_code == 422

    # Turn 3: Gemini failure -> 502 returned cleanly
    r3 = client.post(REPLY_URL.format(session_id=session_id), json={"message": "Query that fails"})
    assert r3.status_code == 502

    # Turn 4: User continues chatting -> succeeds seamlessly
    r4 = client.post(REPLY_URL.format(session_id=session_id), json={"message": "Continuing conversation"})
    assert r4.status_code == 201
    assert r4.json()["content"] == "Recovered reply 3"

    # Verify history integrity in SQLite
    history = client.get(MESSAGES_URL.format(session_id=session_id)).json()
    # Should have: User 1, Bot 1, User 3 (saved before failure), User 4, Bot 4
    assert len(history) == 5
    assert history[0]["content"] == "First query"
    assert history[1]["content"] == "Recovered reply 1"
    assert history[2]["content"] == "Query that fails"
    assert history[3]["content"] == "Continuing conversation"
    assert history[4]["content"] == "Recovered reply 3"
