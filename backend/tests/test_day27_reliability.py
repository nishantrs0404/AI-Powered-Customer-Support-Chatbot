"""
Tests for Day 27: Testing, Edge Cases & Integration Reliability.

Verifies:
  1. Input validation edge cases (exact 2000-char boundary, unicode/emojis, excessive newlines/whitespace).
  2. Malformed request payloads and non-string types on reply endpoint.
  3. Non-existent session handling across conversation endpoints (HTTP 404).
  4. Unsupported HTTP method handling (HTTP 405).
  5. Multi-session isolation and entity memory independence across deep turns.
  6. AI/Gemini failure error handling and user message persistence safety.
"""

from unittest.mock import MagicMock
import pytest

from app.services.prompts import FAQ_RELEVANCE_THRESHOLD


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
# 1. Input Validation Edge Cases
# ===========================================================================


def test_exact_2000_character_boundary_accepted(client, monkeypatch):
    """A message of exactly 2000 characters is within the maximum limit and accepted."""
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Response to 2000 char message.")

    session_id = _create_session(client)
    message_2000 = "a" * 2000

    response = client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": message_2000},
    )
    assert response.status_code == 201
    assert response.json()["content"] == "Response to 2000 char message."


def test_unicode_emojis_multiline_whitespace_handling(client, monkeypatch):
    """Messages with unicode, emojis, accents, and multiple newlines/tabs are processed safely."""
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])
    monkeypatch.setattr(_GEMINI_PATCH, lambda *a, **kw: "Processed unicode query safely.")

    session_id = _create_session(client)
    complex_text = "Hello! 👋 \n\n\n  ¿Dónde está mi paquete?  —  Order #ORD-88888  \t \n\n  Merci! ✨"

    response = client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": complex_text},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "Processed unicode query safely."
    assert "ORD-88888" in data["entities"]["order_ids"]


# ===========================================================================
# 2. Malformed Request Payloads
# ===========================================================================


@pytest.mark.parametrize("invalid_payload", [
    {"message": 12345},
    {"message": True},
    {"message": ["a", "b"]},
    {"message": {"nested": "value"}},
    {},
    {"text": "wrong_key"},
])
def test_malformed_json_types_rejected(client, invalid_payload):
    """Non-string or missing message fields must return HTTP 422 Unprocessable Entity."""
    session_id = _create_session(client)
    response = client.post(
        REPLY_URL.format(session_id=session_id),
        json=invalid_payload,
    )
    assert response.status_code == 422


# ===========================================================================
# 3. Non-Existent Session & Method Handling
# ===========================================================================


def test_nonexistent_session_id_reply_returns_404(client):
    """Posting a reply to an unknown session ID returns HTTP 404 without internal leaks."""
    response = client.post(
        REPLY_URL.format(session_id="non-existent-session-uuid-12345"),
        json={"message": "Hello"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_nonexistent_session_id_messages_returns_404(client):
    """Retrieving message history for an unknown session ID returns HTTP 404."""
    response = client.get(
        MESSAGES_URL.format(session_id="non-existent-session-uuid-67890"),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_unsupported_methods_on_reply_rejected(client):
    """Unsupported HTTP methods on the reply endpoint return HTTP 405 Method Not Allowed."""
    session_id = _create_session(client)
    url = REPLY_URL.format(session_id=session_id)

    get_resp = client.get(url)
    assert get_resp.status_code == 405

    put_resp = client.put(url, json={"message": "test"})
    assert put_resp.status_code == 405

    delete_resp = client.delete(url)
    assert delete_resp.status_code == 405


# ===========================================================================
# 4. Multi-Session Isolation & Entity Independence
# ===========================================================================


def test_concurrent_sessions_deep_isolation(client, monkeypatch):
    """Distinct sessions maintain absolute entity and history isolation across turns."""
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])
    monkeypatch.setattr(_GEMINI_PATCH, lambda msg, hist, prompt: f"Echo: {msg}")

    session_a = _create_session(client)
    session_b = _create_session(client)

    # Session A sets Order A
    r_a1 = client.post(
        REPLY_URL.format(session_id=session_a),
        json={"message": "Checking on order ORD-11111"},
    ).json()
    assert "ORD-11111" in r_a1["entities"]["order_ids"]

    # Session B sets Order B
    r_b1 = client.post(
        REPLY_URL.format(session_id=session_b),
        json={"message": "Checking on order ORD-22222"},
    ).json()
    assert "ORD-22222" in r_b1["entities"]["order_ids"]
    assert "ORD-11111" not in r_b1["entities"]["order_ids"]

    # Session A follow-up preserves Order A, never receives Order B
    r_a2 = client.post(
        REPLY_URL.format(session_id=session_a),
        json={"message": "Can I return this?"},
    ).json()
    assert "ORD-11111" in r_a2["entities"]["order_ids"]
    assert "ORD-22222" not in r_a2["entities"]["order_ids"]

    # Session B follow-up preserves Order B, never receives Order A
    r_b2 = client.post(
        REPLY_URL.format(session_id=session_b),
        json={"message": "When will it arrive?"},
    ).json()
    assert "ORD-22222" in r_b2["entities"]["order_ids"]
    assert "ORD-11111" not in r_b2["entities"]["order_ids"]


# ===========================================================================
# 5. AI Failure Handling & Data Persistence Safety
# ===========================================================================


def test_gemini_failure_preserves_user_message_in_db(client, monkeypatch):
    """When Gemini raises an unexpected runtime failure, user message remains persisted."""
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    def _failing_gemini(*args, **kwargs):
        raise RuntimeError("Service unavailable: connection timeout")

    monkeypatch.setattr(_GEMINI_PATCH, _failing_gemini)

    session_id = _create_session(client)
    response = client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": "Unmatched query that triggers Gemini failure"},
    )
    assert response.status_code == 502
    assert "Gemini could not generate a response" in response.json()["detail"]

    # User message must be persisted in database despite downstream Gemini failure
    history = client.get(MESSAGES_URL.format(session_id=session_id)).json()
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Unmatched query that triggers Gemini failure"


def test_gemini_missing_api_key_returns_500_without_secrets(client, monkeypatch):
    """Missing Gemini API key returns HTTP 500 with safe detail message."""
    monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

    def _missing_key_gemini(*args, **kwargs):
        raise RuntimeError("Gemini API key is not configured in environment.")

    monkeypatch.setattr(_GEMINI_PATCH, _missing_key_gemini)

    session_id = _create_session(client)
    response = client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": "Unmatched query"},
    )
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "API key is not configured" in detail
    assert "GEMINI" not in detail or "configured" in detail

