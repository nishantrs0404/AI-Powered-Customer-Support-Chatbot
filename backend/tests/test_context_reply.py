"""
Tests for the context-aware Gemini reply endpoint.

POST /api/v1/conversations/{session_id}/reply

All Gemini API calls are monkeypatched so the tests do not require a real
API key or network access.
"""

import pytest

from app.services.prompts import HISTORY_LIMIT, SYSTEM_PROMPT


REPLY_URL = "/api/v1/conversations/{session_id}/reply"
# The endpoint imports generate_context_aware_reply directly into app.main,
# so we must patch the name there (not on the gemini module object).
_PATCH_TARGET = "app.main.generate_context_aware_reply"
# The endpoint also imports search_faqs into app.main as faq_service_search;
# patch it there when a test specifically exercises Gemini behaviour and needs
# to suppress any incidental FAQ match.
_FAQ_PATCH_TARGET = "app.main.faq_service_search"




# Helpers



def _create_conversation(client):
    """Create a new conversation and return its session_id and id."""
    response = client.post("/api/v1/conversations")
    assert response.status_code == 201
    data = response.json()
    return data["session_id"], data["id"]


def _send_message(client, session_id: str, content: str) -> dict:
    """Post a user message to the given conversation."""
    response = client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={"message": content},
    )
    assert response.status_code == 201
    return response.json()


def _reply(client, session_id: str, message: str) -> dict:
    """Call the context-aware reply endpoint."""
    return client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": message},
    )


# ---------------------------------------------------------------------------
# System prompt is forwarded to Gemini
# ---------------------------------------------------------------------------


def test_system_prompt_is_passed_to_gemini(client, monkeypatch):
    """The system_prompt argument received by generate_context_aware_reply
    must equal the module-level SYSTEM_PROMPT constant."""
    captured = {}

    def fake_generate(message, history, system_prompt):
        captured["system_prompt"] = system_prompt
        return "Captured."

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)

    session_id, _ = _create_conversation(client)
    response = _reply(client, session_id, "Hello")

    assert response.status_code == 201
    # The augmented prompt now includes format guidance and tone reminder appended
    # after SYSTEM_PROMPT, so we verify the base system prompt is contained in it.
    assert SYSTEM_PROMPT.strip() in captured["system_prompt"]


# ---------------------------------------------------------------------------
# History ordering and content
# ---------------------------------------------------------------------------


def test_previous_messages_passed_in_chronological_order(client, monkeypatch):
    """History must be oldest-first when Gemini receives it."""
    captured = {}

    def fake_generate(message, history, system_prompt):
        captured["history"] = history
        return "Got it."

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)

    session_id, _ = _create_conversation(client)

    # Create two prior user messages via the plain message endpoint.
    _send_message(client, session_id, "First message")
    _send_message(client, session_id, "Second message")

    _reply(client, session_id, "Third message")

    history = captured["history"]
    assert len(history) == 2
    assert history[0]["content"] == "First message"
    assert history[1]["content"] == "Second message"


def test_current_message_not_duplicated_in_history(client, monkeypatch):
    """The message sent to the /reply endpoint must not appear in history.

    search_faqs is patched to return no results so that the Gemini path is
    taken regardless of whether the test message matches a FAQ entry.
    """
    captured = {}

    def fake_generate(message, history, system_prompt):
        captured["message"] = message
        captured["history"] = history
        return "OK."

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)
    # Force the Gemini path so we can inspect the history argument.
    monkeypatch.setattr(_FAQ_PATCH_TARGET, lambda *a, **kw: [])

    session_id, _ = _create_conversation(client)
    current = "What is my order status?"
    _reply(client, session_id, current)

    assert captured["message"] == current
    for entry in captured["history"]:
        assert entry["content"] != current


def test_empty_history_for_first_message(client, monkeypatch):
    """A fresh conversation has no prior history."""
    captured = {}

    def fake_generate(message, history, system_prompt):
        captured["history"] = history
        return "Welcome!"

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)

    session_id, _ = _create_conversation(client)
    response = _reply(client, session_id, "Hi there")

    assert response.status_code == 201
    assert captured["history"] == []


# ---------------------------------------------------------------------------
# History includes assistant replies from previous turns
# ---------------------------------------------------------------------------


def test_assistant_replies_included_in_history(client, monkeypatch):
    """When a previous /reply call stored an assistant message, that message
    should appear in the history for the next call."""
    call_count = {"n": 0}

    def fake_generate(message, history, system_prompt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "First assistant reply."
        # On the second call, capture and verify history.
        call_count["history"] = history
        return "Second assistant reply."

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)

    session_id, _ = _create_conversation(client)
    _reply(client, session_id, "Hello")
    _reply(client, session_id, "Follow-up question")

    history = call_count["history"]
    roles = [entry["role"] for entry in history]
    assert "user" in roles
    assert "assistant" in roles


# ---------------------------------------------------------------------------
# Conversation isolation
# ---------------------------------------------------------------------------


def test_different_conversations_have_isolated_history(client, monkeypatch):
    """Messages from conversation A must never appear in conversation B's history."""
    histories = {}

    def fake_generate(message, history, system_prompt):
        histories[message] = history
        return "Reply."

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)

    session_a, _ = _create_conversation(client)
    session_b, _ = _create_conversation(client)

    _send_message(client, session_a, "Message from conversation A")
    _reply(client, session_b, "Message from conversation B")

    history_b = histories.get("Message from conversation B", [])
    contents = [entry["content"] for entry in history_b]
    assert "Message from conversation A" not in contents


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_reply_returns_404_for_unknown_session(client, monkeypatch):
    monkeypatch.setattr(_PATCH_TARGET, lambda *a, **kw: "Should not be called.")

    response = _reply(client, "nonexistent-session-xyz", "Hello")

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_reply_returns_422_for_empty_message(client):
    session_id, _ = _create_conversation(client)
    response = _reply(client, session_id, "   ")

    assert response.status_code == 422


def test_reply_returns_502_on_gemini_failure(client, monkeypatch):
    def fake_generate(message, history, system_prompt):
        raise RuntimeError("Gemini is temporarily unavailable.")

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)
    # Suppress any FAQ match so the Gemini path (and its error) is reached.
    monkeypatch.setattr(_FAQ_PATCH_TARGET, lambda *a, **kw: [])

    session_id, _ = _create_conversation(client)
    response = _reply(client, session_id, "Help!")

    assert response.status_code == 502
    assert "Gemini" in response.json()["detail"]


def test_reply_returns_500_on_missing_api_key(client, monkeypatch):
    def fake_generate(message, history, system_prompt):
        raise RuntimeError("GEMINI_API_KEY is missing from the .env file.")

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)
    # Suppress any FAQ match so the Gemini path (and its error) is reached.
    monkeypatch.setattr(_FAQ_PATCH_TARGET, lambda *a, **kw: [])

    session_id, _ = _create_conversation(client)
    response = _reply(client, session_id, "Help!")

    assert response.status_code == 500
    assert "not configured" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Response and persistence
# ---------------------------------------------------------------------------


def test_reply_persists_user_and_assistant_messages(client, monkeypatch):
    """Both the user message and the assistant reply must be stored in SQLite."""
    monkeypatch.setattr(_PATCH_TARGET, lambda msg, hist, sp: "Persisted assistant reply.")

    session_id, _ = _create_conversation(client)
    _reply(client, session_id, "Persist me")

    history_response = client.get(
        f"/api/v1/conversations/{session_id}/messages"
    )
    assert history_response.status_code == 200

    messages = history_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Persist me"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Persisted assistant reply."


def test_reply_response_has_correct_shape(client, monkeypatch):
    """The response body must match the MessageResponse schema."""
    monkeypatch.setattr(_PATCH_TARGET, lambda msg, hist, sp: "Shape is correct.")

    session_id, _ = _create_conversation(client)
    response = _reply(client, session_id, "Check schema")

    assert response.status_code == 201
    data = response.json()

    assert data["role"] == "assistant"
    assert data["content"] == "Shape is correct."
    assert "id" in data
    assert "conversation_id" in data
    assert "created_at" in data


def test_reply_messages_ordered_correctly_in_db(client, monkeypatch):
    """After two /reply calls the stored messages must be in insertion order."""
    replies = ["First AI answer.", "Second AI answer."]
    call_index = {"i": 0}

    def fake_generate(message, history, system_prompt):
        reply = replies[call_index["i"]]
        call_index["i"] += 1
        return reply

    monkeypatch.setattr(_PATCH_TARGET, fake_generate)
    # Suppress any FAQ match so the Gemini ordering logic is exercised.
    monkeypatch.setattr(_FAQ_PATCH_TARGET, lambda *a, **kw: [])

    session_id, _ = _create_conversation(client)
    _reply(client, session_id, "Question one")
    _reply(client, session_id, "Question two")

    history_response = client.get(
        f"/api/v1/conversations/{session_id}/messages"
    )
    messages = history_response.json()

    assert messages[0]["content"] == "Question one"
    assert messages[1]["content"] == "First AI answer."
    assert messages[2]["content"] == "Question two"
    assert messages[3]["content"] == "Second AI answer."
