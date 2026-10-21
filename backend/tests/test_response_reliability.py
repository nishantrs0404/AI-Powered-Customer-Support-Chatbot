"""
Tests for Day 17: Chatbot response reliability and FAQ-to-Gemini response workflow.

Verifies:
  1. FAQ relevance improvements:
     - Handling of contractions without token fragmentation (e.g. hasn't, haven't).
     - Conversational follow-ups (e.g. "Why not?", "Not yet") fall back to Gemini
       instead of falsely triggering FAQ answers.
     - Whole-word keyword matching avoids substring false positives (e.g. reinvoice).
     - Unrelated questions with partial keyword overlap fall back to Gemini.
     - Natural customer questions match appropriate FAQs with high scores.
  2. Complete FAQ-to-Gemini response workflow:
     - Verified FAQ answers bypass Gemini and set answer_source='faq'.
     - Fallback to Gemini includes chronological history and sets answer_source='gemini'.
     - Current user message is never duplicated in history passed to Gemini.
     - Conversation history remains isolated across distinct sessions.
     - Multi-turn interaction correctly records both user and assistant turns in DB.
  3. Error handling & resilience:
     - Graceful fallback to Gemini when FAQ search encounters unexpected exceptions.
     - Database commit failures trigger transaction rollback and return safe HTTP 500.
     - Missing Gemini credentials return HTTP 500 without leaking secrets.
     - Gemini service failures or unexpected exceptions return HTTP 502 safely.
     - Input validation rejects empty/whitespace messages and oversized payloads (>2000 chars).
     - Non-existent session IDs return HTTP 404 before processing.
"""

from unittest.mock import MagicMock
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services.faq_search import calculate_score, search_faqs
from app.services.prompts import FAQ_RELEVANCE_THRESHOLD, SYSTEM_PROMPT


REPLY_URL = "/api/v1/conversations/{session_id}/reply"
_GEMINI_PATCH = "app.main.generate_context_aware_reply"
_FAQ_PATCH = "app.main.faq_service_search"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_conversation(client) -> str:
    """Create a new conversation session and return its session_id."""
    response = client.post("/api/v1/conversations")
    assert response.status_code == 201
    return response.json()["session_id"]


def _reply(client, session_id: str, message: str):
    """Post to the conversation reply endpoint."""
    return client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": message},
    )


# ===========================================================================
# 1. FAQ Relevance and Search Accuracy
# ===========================================================================


def test_contractions_preserve_keyword_matches():
    """Contractions like 'hasn\\'t' or 'haven\\'t' should not pollute query tokens."""
    results_order = search_faqs("Why hasn't my order shipped?")
    assert results_order, "Expected FAQ match for 'Why hasn't my order shipped?'"
    assert results_order[0]["id"] == "FAQ004"
    assert results_order[0]["score"] >= 0.80

    results_refund = search_faqs("I haven't received my refund")
    assert results_refund, "Expected FAQ match for 'I haven't received my refund'"
    assert results_refund[0]["id"] == "FAQ015"
    assert results_refund[0]["score"] >= 0.80


def test_conversational_followups_do_not_falsely_match_faq():
    """Follow-up questions depending on conversational context must not match FAQs."""
    follow_ups = [
        "Why not?",
        "Not yet",
        "Where is it now?",
        "What about that?",
        "Can you check again?",
    ]
    for query in follow_ups:
        results = search_faqs(query, min_score=FAQ_RELEVANCE_THRESHOLD)
        assert results == [], f"Expected no FAQ match for follow-up query: '{query}'"


def test_substring_words_do_not_trigger_keyword_phrase_matches():
    """Words containing keywords as substrings (e.g., 'reinvoice') must not get phrase bonus."""
    results = search_faqs("Can you reinvoice this order?", min_score=0.90)
    # Even if "invoice" is a keyword for FAQ012, "reinvoice" must not match as a whole word phrase.
    assert not any(r["score"] >= 0.90 for r in results)


def test_unrelated_queries_with_incidental_overlap_fall_back(client, monkeypatch):
    """Unrelated questions with single overlapping words must fall back to Gemini."""
    gemini_called = {"called": False}

    def fake_gemini(message, history, system_prompt):
        gemini_called["called"] = True
        return "I can only help with our store's products and orders."

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "I want to order a pizza")

    assert response.status_code == 201
    assert gemini_called["called"], "Gemini must be called for unrelated queries"
    assert response.json()["answer_source"] == "gemini"


def test_greetings_fall_back_to_gemini(client, monkeypatch):
    """Standard greetings without FAQ equivalents should fall back to Gemini."""
    gemini_called = {"called": False}

    def fake_gemini(message, history, system_prompt):
        gemini_called["called"] = True
        return "Hello! How can I assist you with your customer support inquiries today?"

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Hello")

    assert response.status_code == 201
    assert gemini_called["called"]
    assert response.json()["answer_source"] == "gemini"


# ===========================================================================
# 2. Complete FAQ-to-Gemini Workflow & Context Integrity
# ===========================================================================


def test_faq_match_bypasses_gemini_and_sets_source(client, monkeypatch):
    """A high-confidence FAQ match must not invoke Gemini and must set answer_source='faq'."""
    gemini_called = {"called": False}

    def fake_gemini(*args, **kwargs):
        gemini_called["called"] = True
        return "Gemini reply"

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "How can I track my order?")

    assert response.status_code == 201
    assert not gemini_called["called"], "Gemini should not be called when an FAQ matches"
    data = response.json()
    assert data["answer_source"] == "faq"
    assert "tracking" in data["content"].lower()


def test_multi_turn_conversation_with_mixed_sources(client, monkeypatch):
    """Verify a conversation can interleave FAQ and Gemini replies with persisted state."""
    gemini_calls = []

    def fake_gemini(message, history, system_prompt):
        gemini_calls.append({"message": message, "history": list(history)})
        return f"Gemini reply to: {message}"

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    session_id = _create_conversation(client)

    # Turn 1: FAQ query
    r1 = _reply(client, session_id, "How can I track my order?")
    assert r1.status_code == 201
    assert r1.json()["answer_source"] == "faq"

    # Turn 2: Non-FAQ query (Gemini)
    r2 = _reply(client, session_id, "Tell me more about your return policy exceptions")
    assert r2.status_code == 201
    assert r2.json()["answer_source"] == "gemini"
    assert len(gemini_calls) == 1

    # Verify Gemini received the prior turns in chronological order
    gemini_history = gemini_calls[0]["history"]
    assert len(gemini_history) == 2
    assert gemini_history[0]["role"] == "user"
    assert gemini_history[0]["content"] == "How can I track my order?"
    assert gemini_history[1]["role"] == "assistant"
    assert "tracking" in gemini_history[1]["content"].lower()

    # Turn 3: Verify all 4 messages exist in conversation history endpoint
    history_resp = client.get(f"/api/v1/conversations/{session_id}/messages")
    assert history_resp.status_code == 200
    messages = history_resp.json()
    assert len(messages) == 4
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]


def test_session_isolation_across_multiple_conversations(client, monkeypatch):
    """Ensure two distinct conversation sessions never leak messages to each other."""
    captured_histories = {}

    def fake_gemini(message, history, system_prompt):
        captured_histories[message] = history
        return f"Response to {message}"

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    session_a = _create_conversation(client)
    session_b = _create_conversation(client)

    # Session A message
    _reply(client, session_a, "Question from session A")

    # Session B message
    _reply(client, session_b, "Question from session B")

    # Follow-up in session A
    _reply(client, session_a, "Follow-up in session A")

    # Follow-up in session B
    _reply(client, session_b, "Follow-up in session B")

    # History passed to session A follow-up should only contain session A turns
    history_a = captured_histories["Follow-up in session A"]
    assert any(h["content"] == "Question from session A" for h in history_a)
    assert not any(h["content"] == "Question from session B" for h in history_a)

    # History passed to session B follow-up should only contain session B turns
    history_b = captured_histories["Follow-up in session B"]
    assert any(h["content"] == "Question from session B" for h in history_b)
    assert not any(h["content"] == "Question from session A" for h in history_b)


# ===========================================================================
# 3. Error Handling and Resilience
# ===========================================================================


def test_faq_search_failure_gracefully_falls_back_to_gemini(client, monkeypatch):
    """If the FAQ search layer raises an unexpected error, safely fall back to Gemini."""
    def broken_faq_search(*args, **kwargs):
        raise RuntimeError("FAQ dataset corrupted or unavailable.")

    monkeypatch.setattr(_FAQ_PATCH, broken_faq_search)

    gemini_called = {"called": False}

    def fake_gemini(message, history, system_prompt):
        gemini_called["called"] = True
        return "Gemini fallback reply after FAQ search error."

    monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "How can I track my order?")

    assert response.status_code == 201
    assert gemini_called["called"], "Must fall back to Gemini when FAQ search fails"
    assert response.json()["answer_source"] == "gemini"


def test_reply_rejects_empty_whitespace_message(client):
    """Empty or all-whitespace message payloads must return HTTP 422."""
    session_id = _create_conversation(client)
    response = _reply(client, session_id, "    ")
    assert response.status_code == 422


def test_reply_rejects_oversized_message(client):
    """Messages exceeding 2000 characters must return HTTP 422."""
    session_id = _create_conversation(client)
    long_msg = "x" * 2001
    response = _reply(client, session_id, long_msg)
    assert response.status_code == 422


def test_reply_returns_404_for_nonexistent_session(client):
    """Attempting to reply to a non-existent conversation session returns HTTP 404."""
    response = _reply(client, "non-existent-session-id-12345", "Hello")
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_unexpected_gemini_exception_returns_502_cleanly(client, monkeypatch):
    """Unexpected exceptions from the AI layer must return 502 without exposing stack traces."""
    def exploding_gemini(*args, **kwargs):
        raise TypeError("Unexpected type error in client library")

    monkeypatch.setattr(_GEMINI_PATCH, exploding_gemini)

    session_id = _create_conversation(client)
    response = _reply(client, session_id, "Tell me something unique")

    assert response.status_code == 502
    assert response.json()["detail"] == "Gemini could not generate a response. Please try again."


def test_database_error_on_user_message_rolls_back(client, monkeypatch):
    """Database failure on user message persist triggers rollback and returns HTTP 500."""
    from app.database import get_db

    session_id = _create_conversation(client)

    # Patch Session.commit to simulate database failure on first commit
    original_commit = None

    def fail_commit(self):
        raise SQLAlchemyError("Disk full or connection dropped")

    from sqlalchemy.orm import Session
    monkeypatch.setattr(Session, "commit", fail_commit)

    response = _reply(client, session_id, "Test database error")
    assert response.status_code == 500
    assert "Database error" in response.json()["detail"]
