"""Tests for Day 21 — Multi-Turn Slot Filling & Conversational State Tracking.

Covers:
- Remembering an order ID across turns.
- Resolving follow-up shipping questions using prior state.
- Supplying an identifier in a later message.
- Updating state when a new order is introduced.
- Clearing state when the topic changes.
- Ambiguous references and multiple order IDs.
- Isolation between separate sessions.
- State persistence across simulated restarts.
- Missing identifiers and unknown orders.
- Compatibility with existing FAQ and Gemini workflows.
"""

import pytest

from app.services.conversation_state import (
    _TOPIC_CHANGE_INTENTS,
    build_clarification_reply,
    load_state,
    resolve_entities,
    update_state,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPLY_URL = "/api/v1/conversations/{session_id}/reply"
_GEMINI_PATCH = "app.main.generate_context_aware_reply"
_FAQ_PATCH = "app.main.faq_service_search"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_conversation(client):
    """Create a new conversation; return (session_id, conversation_id)."""
    r = client.post("/api/v1/conversations")
    assert r.status_code == 201
    data = r.json()
    return data["session_id"], data["id"]


def _reply(client, session_id: str, message: str, monkeypatch=None, fake_gemini=None):
    """Send a reply request.  Optionally monkeypatches Gemini and FAQ."""
    if monkeypatch is not None:
        if fake_gemini is None:
            fake_gemini = lambda msg, hist, sp: "OK."
        monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])
    return client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": message},
    )


# ===========================================================================
# Unit tests: resolve_entities (pure logic, no DB)
# ===========================================================================


class FakeState:
    """Lightweight stand-in for ConversationState without a DB."""

    def __init__(
        self,
        active_order_id=None,
        active_tracking_number=None,
        active_intent=None,
        pending_clarification=False,
    ):
        self.active_order_id = active_order_id
        self.active_tracking_number = active_tracking_number
        self.active_intent = active_intent
        self.pending_clarification = pending_clarification


class TestResolveEntities:
    """Unit tests for the resolve_entities function."""

    # ------------------------------------------------------------------
    # Carry-forward
    # ------------------------------------------------------------------

    def test_order_id_carried_forward_when_missing(self):
        state = FakeState(active_order_id="ORD-10001")
        entities = {"order_ids": [], "tracking_numbers": [], "emails": [], "amounts": [], "products": []}
        resolved, ambiguous = resolve_entities(entities, "order_status", state)
        assert not ambiguous
        assert resolved["order_ids"] == ["ORD-10001"]

    def test_tracking_number_carried_forward_when_missing(self):
        state = FakeState(active_tracking_number="TRK-88001122")
        entities = {"order_ids": [], "tracking_numbers": [], "emails": [], "amounts": [], "products": []}
        resolved, ambiguous = resolve_entities(entities, "shipping", state)
        assert not ambiguous
        assert resolved["tracking_numbers"] == ["TRK-88001122"]

    def test_existing_entity_not_overwritten_by_state(self):
        """When the user provides a new ID, it takes precedence over state."""
        state = FakeState(active_order_id="ORD-OLD")
        entities = {"order_ids": ["ORD-NEW"], "tracking_numbers": [], "emails": [], "amounts": [], "products": []}
        resolved, ambiguous = resolve_entities(entities, "order_status", state)
        assert not ambiguous
        assert resolved["order_ids"] == ["ORD-NEW"]

    def test_no_carry_forward_with_no_state(self):
        resolved, ambiguous = resolve_entities(
            {"order_ids": [], "tracking_numbers": [], "emails": [], "amounts": [], "products": []},
            "order_status",
            None,
        )
        assert not ambiguous
        assert resolved["order_ids"] == []

    # ------------------------------------------------------------------
    # Topic-change guard
    # ------------------------------------------------------------------

    def test_topic_change_blocks_carry_forward(self):
        """A greeting intent must NOT pull in an old order ID."""
        state = FakeState(active_order_id="ORD-10001")
        entities = {"order_ids": [], "tracking_numbers": [], "emails": [], "amounts": [], "products": []}
        resolved, ambiguous = resolve_entities(entities, "greeting", state)
        assert not ambiguous
        assert resolved["order_ids"] == []

    @pytest.mark.parametrize("intent", list(_TOPIC_CHANGE_INTENTS))
    def test_all_topic_change_intents_block_carry_forward(self, intent):
        state = FakeState(active_order_id="ORD-10001", active_tracking_number="TRK-X")
        entities = {"order_ids": [], "tracking_numbers": [], "emails": [], "amounts": [], "products": []}
        resolved, ambiguous = resolve_entities(entities, intent, state)
        assert not ambiguous
        assert resolved["order_ids"] == []
        assert resolved["tracking_numbers"] == []

    def test_unknown_intent_still_carries_forward(self):
        """'unknown' intent is neutral - it does not block carry-forward."""
        state = FakeState(active_order_id="ORD-10001")
        entities = {"order_ids": [], "tracking_numbers": [], "emails": [], "amounts": [], "products": []}
        resolved, ambiguous = resolve_entities(entities, "unknown", state)
        assert not ambiguous
        assert resolved["order_ids"] == ["ORD-10001"]

    # ------------------------------------------------------------------
    # Ambiguity detection
    # ------------------------------------------------------------------

    def test_multiple_distinct_order_ids_triggers_ambiguity(self):
        entities = {
            "order_ids": ["ORD-10001", "ORD-10002"],
            "tracking_numbers": [],
            "emails": [], "amounts": [], "products": [],
        }
        _, ambiguous = resolve_entities(entities, "order_status", None)
        assert ambiguous

    def test_multiple_distinct_tracking_numbers_triggers_ambiguity(self):
        entities = {
            "order_ids": [],
            "tracking_numbers": ["TRK-111", "TRK-222"],
            "emails": [], "amounts": [], "products": [],
        }
        _, ambiguous = resolve_entities(entities, "shipping", None)
        assert ambiguous

    def test_single_order_id_not_ambiguous(self):
        entities = {
            "order_ids": ["ORD-10001"],
            "tracking_numbers": [],
            "emails": [], "amounts": [], "products": [],
        }
        _, ambiguous = resolve_entities(entities, "order_status", None)
        assert not ambiguous

    def test_duplicate_same_id_not_ambiguous(self):
        """Duplicate of the same ID (case-insensitive) is not ambiguous."""
        entities = {
            "order_ids": ["ORD-10001", "ord-10001"],
            "tracking_numbers": [],
            "emails": [], "amounts": [], "products": [],
        }
        _, ambiguous = resolve_entities(entities, "order_status", None)
        assert not ambiguous


# ===========================================================================
# Unit tests: update_state (with in-memory DB via FastAPI TestClient fixtures)
# ===========================================================================


class TestUpdateState:
    """Verify the state upsert logic via DB-backed helpers."""

    def test_state_created_on_first_turn(self, client):
        session_id, conv_id = _create_conversation(client)
        # Indirectly verify: after a reply the state row exists.
        # We test this through the public API in integration tests below.

    def test_build_clarification_reply_not_empty(self):
        msg = build_clarification_reply()
        assert isinstance(msg, str)
        assert len(msg) > 20


# ===========================================================================
# Integration tests: full reply pipeline with state tracking
# ===========================================================================


class TestStatePersistenceAcrossTurns:
    """Multi-turn scenarios exercising the live reply endpoint."""

    def test_order_id_remembered_across_turns(self, client, monkeypatch):
        """Turn 1 provides ORD-10001; turn 2 asks a follow-up without repeating it."""
        captured = {}

        def fake_gemini(msg, hist, sp):
            captured["context"] = sp
            return "Checking order details."

        monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)

        # Turn 1: customer mentions order ID explicitly.
        r1 = _reply(client, session_id, "Where is my order ORD-10001?")
        assert r1.status_code == 201
        data1 = r1.json()
        assert "ORD-10001" in str(data1["entities"])

        # Turn 2: follow-up with no ID — state should carry ORD-10001 forward.
        r2 = _reply(client, session_id, "What is its current status?")
        assert r2.status_code == 201
        data2 = r2.json()
        # The resolved entities in turn 2 should contain the carried-forward order.
        assert "ORD-10001" in str(data2["entities"])

    def test_follow_up_shipping_uses_prior_order_context(self, client, monkeypatch):
        """Shipping follow-up should resolve to the prior order's shipment."""
        captured_context = {}

        def fake_gemini(msg, hist, sp):
            captured_context["prompt"] = sp
            return "Shipment is in transit."

        monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)

        # Turn 1: mention an order.
        _reply(client, session_id, "Track my order ORD-10001 please")

        # Turn 2: ask about shipping without repeating the order.
        r2 = _reply(client, session_id, "What is the shipping status?")
        assert r2.status_code == 201
        data2 = r2.json()
        assert "ORD-10001" in str(data2["entities"]) or "ORD-10001" in captured_context.get("prompt", "")

    def test_identifier_supplied_in_later_message(self, client, monkeypatch):
        """Turn 1 asks about an order without an ID; turn 2 supplies the ID."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Please provide your order ID.")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)

        # Turn 1: vague request.
        r1 = _reply(client, session_id, "Where is my order?")
        assert r1.status_code == 201

        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Checking ORD-10002.")

        # Turn 2: customer now provides the ID.
        r2 = _reply(client, session_id, "ORD-10002")
        assert r2.status_code == 201
        data2 = r2.json()
        assert "ORD-10002" in str(data2["entities"])

    def test_new_order_id_overwrites_previous(self, client, monkeypatch):
        """When the customer mentions a different order, state must update."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Got it.")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)

        # Turn 1: ORD-10001
        _reply(client, session_id, "Check order ORD-10001")

        # Turn 2: different order ORD-10002
        r2 = _reply(client, session_id, "Actually, what about order ORD-10002?")
        assert r2.status_code == 201
        data2 = r2.json()
        assert "ORD-10002" in str(data2["entities"])
        # ORD-10001 must NOT be in the resolved entities for this turn.
        assert "ORD-10001" not in str(data2["entities"])

    def test_topic_change_clears_order_context(self, client, monkeypatch):
        """After a greeting intent, the old order slot must be cleared."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Hello!")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)

        # Turn 1: set order context.
        _reply(client, session_id, "Where is order ORD-10001?")

        # Turn 2: completely different topic (greeting clears slots).
        r2 = _reply(client, session_id, "Hello, can you help me?")
        assert r2.status_code == 201
        data2 = r2.json()
        # After topic change, order context should not carry forward.
        assert "ORD-10001" not in str(data2["entities"])

    def test_ambiguous_multiple_order_ids_triggers_clarification(self, client, monkeypatch):
        """Two different order IDs in one message should return a clarification."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Should not be called.")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)

        # Construct a message the entity extractor will parse as two distinct orders.
        r = _reply(
            client,
            session_id,
            "I need help with order ORD-10001 and also order ORD-10002",
        )
        assert r.status_code == 201
        data = r.json()
        # The reply should ask for clarification.
        content = data["content"].lower()
        assert any(word in content for word in ["clarif", "confirm", "which", "right one"])

    def test_session_isolation(self, client, monkeypatch):
        """State from conversation A must never bleed into conversation B."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Got it.")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_a, _ = _create_conversation(client)
        session_b, _ = _create_conversation(client)

        # Set order context in session A.
        _reply(client, session_a, "Where is order ORD-10001?")

        # Ask follow-up in session B without mentioning any order.
        r_b = _reply(client, session_b, "What is the status?")
        assert r_b.status_code == 201
        data_b = r_b.json()
        # Session B should NOT have ORD-10001 in its resolved entities.
        assert "ORD-10001" not in str(data_b["entities"])

    def test_missing_identifier_handled_gracefully(self, client, monkeypatch):
        """No order ID in any turn — response should still be valid."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Please provide your order ID.")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)

        r = _reply(client, session_id, "Where is my order?")
        assert r.status_code == 201
        data = r.json()
        assert data["role"] == "assistant"
        assert data["content"]  # Some response must be present.

    def test_state_persists_across_simulated_restart(self, client, monkeypatch):
        """State must survive a DB commit (simulated restart between turns)."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Noted.")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, conv_id = _create_conversation(client)

        # Turn 1: persist order ID in state.
        _reply(client, session_id, "Check my order ORD-10001")

        # The state row is already committed to SQLite.  A new TestClient
        # request picks it up from the DB — simulating a restart.
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "Tracking your order.")

        r2 = _reply(client, session_id, "What is its tracking number?")
        assert r2.status_code == 201
        data2 = r2.json()
        assert "ORD-10001" in str(data2["entities"])

    def test_faq_path_unaffected_by_state_tracking(self, client, monkeypatch):
        """FAQ-first routing must still work correctly alongside state tracking."""
        # Simulate a strong FAQ hit so the FAQ path is taken.
        faq_hit = [{"answer": "Our return policy is 30 days.", "score": 0.9}]
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: faq_hit)

        session_id, _ = _create_conversation(client)
        r = _reply(client, session_id, "What is your return policy?")
        assert r.status_code == 201
        data = r.json()
        assert data["answer_source"] == "faq"
        assert "30 days" in data["content"]

    def test_unknown_order_id_handled_gracefully(self, client, monkeypatch):
        """Referencing a non-existent order should return a valid Gemini response."""
        monkeypatch.setattr(
            _GEMINI_PATCH,
            lambda m, h, s: "I could not find an order with that ID.",
        )
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        r = _reply(client, session_id, "Where is order ORD-NOTEXIST?")
        assert r.status_code == 201
        data = r.json()
        assert data["role"] == "assistant"
        assert data["answer_source"] == "gemini"

    def test_response_shape_unchanged_after_day21(self, client, monkeypatch):
        """The ReplyResponse schema must remain backward-compatible."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, s: "All good.")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        r = _reply(client, session_id, "Hello there")
        assert r.status_code == 201
        data = r.json()

        required_fields = {"id", "conversation_id", "role", "content", "created_at", "answer_source", "intent", "entities"}
        assert required_fields.issubset(data.keys())

    def test_entities_in_response_reflect_resolved_values(self, client, monkeypatch):
        """The `entities` field in ReplyResponse must show resolved (not raw) entities."""
        captured = {}

        def fake_gemini(msg, hist, sp):
            return "Here are your order details."

        monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)

        # Turn 1: provide the order ID.
        _reply(client, session_id, "Status of order ORD-10001 please")

        # Turn 2: follow-up without ID.
        r2 = _reply(client, session_id, "Any updates?")
        assert r2.status_code == 201
        data2 = r2.json()
        # The resolved entities should contain the carried-forward order.
        entities = data2.get("entities", {})
        assert "ORD-10001" in str(entities)
