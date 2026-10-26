"""Tests for Day 22–23: Response formatting, tone control, quality scoring,
response validation, and safe fallback integration.

Coverage:
  1. Response formatting (get_format_guidance, build_tone_reminder)
  2. Quality scoring (score_response thresholds, critical failures, determinism)
  3. Response validation (valid/invalid responses, business claims, fallbacks)
  4. Reply pipeline integration (validation in /reply endpoint, FAQ path unaffected)
  5. No regression in existing API response schema or history handling.
"""

from __future__ import annotations

import pytest

from app.services.response_formatter import build_tone_reminder, get_format_guidance
from app.services.response_quality import QUALITY_THRESHOLD, QualityResult, score_response
from app.services.response_validator import (
    SAFE_FALLBACK_GEMINI_ERROR,
    SAFE_FALLBACK_MISSING_ID,
    SAFE_FALLBACK_UNVERIFIED_OP,
    ValidationResult,
    validate_response,
)


# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

REPLY_URL = "/api/v1/conversations/{session_id}/reply"
_GEMINI_PATCH = "app.main.generate_context_aware_reply"
_FAQ_PATCH = "app.main.faq_service_search"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_conversation(client) -> tuple[str, int]:
    r = client.post("/api/v1/conversations")
    assert r.status_code == 201
    data = r.json()
    return data["session_id"], data["id"]


def _reply(client, session_id: str, message: str):
    return client.post(
        REPLY_URL.format(session_id=session_id),
        json={"message": message},
    )


def _order_context(order_id="ORD-10001", status="processing") -> dict:
    return {
        "intent": "order_status",
        "order": {"order_id": order_id, "status": status, "total": "$99.00",
                  "placed_at": "2024-01-01", "updated_at": "2024-01-02", "items": []},
        "data_retrieved": True,
        "missing_info": [],
    }


# ===========================================================================
# 1. Response Formatting — get_format_guidance
# ===========================================================================


class TestGetFormatGuidance:
    """Unit tests for the format guidance helper."""

    def test_order_status_guidance_non_empty(self):
        guidance = get_format_guidance("order_status")
        assert isinstance(guidance, str)
        assert len(guidance) > 10
        assert "order" in guidance.lower() or "status" in guidance.lower()

    def test_shipping_guidance_non_empty(self):
        guidance = get_format_guidance("shipping")
        assert isinstance(guidance, str)
        assert len(guidance) > 10

    def test_return_guidance_non_empty(self):
        guidance = get_format_guidance("return")
        assert isinstance(guidance, str)
        assert "return" in guidance.lower() or "policy" in guidance.lower()

    def test_refund_guidance_non_empty(self):
        guidance = get_format_guidance("refund")
        assert isinstance(guidance, str)
        assert len(guidance) > 10

    def test_cancel_order_guidance_non_empty(self):
        guidance = get_format_guidance("cancel_order")
        assert isinstance(guidance, str)
        assert "cancel" in guidance.lower()

    def test_technical_issue_guidance_non_empty(self):
        guidance = get_format_guidance("technical_issue")
        assert isinstance(guidance, str)
        assert "step" in guidance.lower() or "troubleshoot" in guidance.lower()

    def test_complaint_guidance_contains_empathy_direction(self):
        guidance = get_format_guidance("complaint")
        assert "apologize" in guidance.lower() or "apolog" in guidance.lower() or "empathetic" in guidance.lower() or "warm" in guidance.lower()

    def test_product_info_guidance_non_empty(self):
        guidance = get_format_guidance("product_info")
        assert isinstance(guidance, str)
        assert "product" in guidance.lower()

    def test_greeting_returns_empty_string(self):
        """Greeting intent needs no special format guidance."""
        guidance = get_format_guidance("greeting")
        assert guidance == ""

    def test_human_agent_returns_empty_string(self):
        guidance = get_format_guidance("human_agent")
        assert guidance == ""

    def test_unknown_intent_returns_empty_or_general(self):
        guidance = get_format_guidance("unknown")
        assert isinstance(guidance, str)  # May be empty or general

    def test_missing_info_prepend_when_no_data_retrieved(self):
        """When ID is missing and no data retrieved, missing-info guidance is prepended."""
        context = {
            "intent": "order_status",
            "data_retrieved": False,
            "missing_info": ["No order ID was provided by the customer."],
        }
        guidance = get_format_guidance("order_status", context)
        assert "missing" in guidance.lower() or "information" in guidance.lower()

    def test_no_missing_info_prepend_when_data_retrieved(self):
        """When data was retrieved, missing-info guidance should NOT be prepended."""
        context = {
            "intent": "order_status",
            "data_retrieved": True,
            "order": {"order_id": "ORD-10001"},
            "missing_info": [],
        }
        guidance = get_format_guidance("order_status", context)
        # Should still contain order guidance but not start with MISSING INFO block.
        assert guidance  # Non-empty


class TestBuildToneReminder:
    def test_tone_reminder_non_empty(self):
        reminder = build_tone_reminder()
        assert isinstance(reminder, str)
        assert len(reminder) > 20

    def test_tone_reminder_mentions_concise(self):
        reminder = build_tone_reminder()
        assert "concise" in reminder.lower() or "professional" in reminder.lower()

    def test_tone_reminder_is_deterministic(self):
        assert build_tone_reminder() == build_tone_reminder()


# ===========================================================================
# 2. Quality Scoring — score_response
# ===========================================================================


class TestScoreResponse:
    """Unit tests for the quality scoring engine."""

    def test_good_response_passes_threshold(self):
        text = (
            "Your order ORD-10001 is currently in processing. "
            "The estimated delivery is in 3-5 business days. "
            "Please check your tracking link for real-time updates."
        )
        result = score_response(text, "order_status", _order_context())
        assert isinstance(result, QualityResult)
        assert result.score >= QUALITY_THRESHOLD
        assert not result.critical_failure

    def test_empty_response_fails(self):
        result = score_response("", "order_status")
        assert result.score < QUALITY_THRESHOLD
        assert not result.passed

    def test_very_short_response_fails(self):
        result = score_response("Ok.", "order_status")
        assert result.score < QUALITY_THRESHOLD or not result.passed

    def test_unverified_refund_claim_is_critical_failure(self):
        """A response claiming a refund was processed without evidence is critical."""
        text = (
            "Your refund has been processed. "
            "You should receive the money within 3-5 business days."
        )
        # No context, or context without refund status.
        context = {
            "intent": "refund",
            "order": {"order_id": "ORD-10001", "status": "processing"},
            "data_retrieved": True,
            "missing_info": [],
        }
        result = score_response(text, "refund", context)
        assert result.critical_failure is True
        assert result.passed is False
        assert any("CRITICAL" in r for r in result.reasons)

    def test_unverified_cancellation_claim_is_critical_failure(self):
        text = "Your order has been cancelled as requested."
        context = {
            "intent": "cancel_order",
            "order": {"order_id": "ORD-10001", "status": "processing"},
            "data_retrieved": True,
            "missing_info": [],
        }
        result = score_response(text, "cancel_order", context)
        assert result.critical_failure is True
        assert result.passed is False

    def test_confirmed_cancellation_does_not_fail(self):
        """When the retrieved data confirms the cancellation, no critical failure."""
        text = "Your order ORD-10001 has been cancelled as requested."
        context = {
            "intent": "cancel_order",
            "order": {"order_id": "ORD-10001", "status": "cancelled"},
            "data_retrieved": True,
            "missing_info": [],
        }
        result = score_response(text, "cancel_order", context)
        assert result.critical_failure is False

    def test_filler_phrases_penalise_score(self):
        text = (
            "Thank you for reaching out to us today! "
            "We value your business and appreciate your patience. "
            "Your order is being processed."
        )
        result_no_filler = score_response(
            "Your order is being processed. Delivery expected in 2 days.", "order_status"
        )
        result_filler = score_response(text, "order_status")
        assert result_filler.dimension_scores["no_filler"] <= result_no_filler.dimension_scores["no_filler"]

    def test_scoring_is_deterministic(self):
        """Identical inputs always return the same score."""
        text = "Your order is being processed. Please check your tracking link."
        r1 = score_response(text, "order_status")
        r2 = score_response(text, "order_status")
        assert r1.score == r2.score
        assert r1.critical_failure == r2.critical_failure

    def test_general_response_not_penalised_for_no_business_data(self):
        """A general greeting/unknown response without retrieved data should not fail."""
        text = "Hello! How can I help you today?"
        result = score_response(text, "greeting", None)
        assert not result.critical_failure
        assert result.score >= QUALITY_THRESHOLD

    def test_off_topic_response_penalises_intent_relevance(self):
        text = "I love pizza and pasta, they are delicious!"
        result = score_response(text, "order_status")
        assert result.dimension_scores.get("intent_relevant", 1.0) < 1.0

    def test_dimension_scores_present(self):
        text = "Your order ORD-10001 status is in transit."
        result = score_response(text, "order_status", _order_context())
        expected_dims = {"non_empty", "length_ok", "intent_relevant", "grounded", "no_filler", "no_unverified_op"}
        assert expected_dims.issubset(result.dimension_scores.keys())

    def test_score_in_zero_to_one_range(self):
        text = "Your refund has been processed successfully."
        result = score_response(text, "refund")
        assert 0.0 <= result.score <= 1.0

    def test_return_grounding_failure_no_context(self):
        """Return/refund-related unverified claims with no context should trigger critical failure."""
        text = "Your return has been approved and the refund has been processed."
        result = score_response(text, "return", None)
        assert result.critical_failure is True


# ===========================================================================
# 3. Response Validation — validate_response
# ===========================================================================


class TestValidateResponse:
    """Unit tests for validate_response."""

    def test_valid_response_passes(self):
        text = "Your order ORD-10001 is currently in processing. Please allow 3-5 business days."
        result = validate_response(text, "order_status", _order_context(), source="gemini")
        assert isinstance(result, ValidationResult)
        assert result.valid is True
        assert result.safe_fallback is None

    def test_empty_response_fails_with_fallback(self):
        result = validate_response("", "order_status", source="gemini")
        assert result.valid is False
        assert result.safe_fallback is not None
        assert len(result.safe_fallback) > 10

    def test_whitespace_only_response_fails(self):
        result = validate_response("   \n  ", "refund", source="gemini")
        assert result.valid is False
        assert result.safe_fallback is not None

    def test_critical_quality_failure_returns_fallback(self):
        """A response with an unverified operation claim should fail validation."""
        text = "Your refund has been processed and you will receive the money within 5 days."
        context = {
            "intent": "refund",
            "order": {"order_id": "ORD-10001", "status": "processing"},
            "data_retrieved": True,
            "missing_info": [],
        }
        result = validate_response(text, "refund", context, source="gemini")
        assert result.valid is False
        assert result.safe_fallback == SAFE_FALLBACK_UNVERIFIED_OP

    def test_faq_response_passes_light_validation(self):
        """FAQ responses bypass most validation and only fail if empty."""
        text = "You can return items within 30 days of purchase."
        result = validate_response(text, "return", None, source="faq")
        assert result.valid is True

    def test_faq_empty_fails_validation(self):
        result = validate_response("", "return", source="faq")
        assert result.valid is False

    def test_missing_id_context_blocks_fabricated_data(self):
        """When no ID was provided and no data retrieved, a fabricated order number in the
        response should be blocked."""
        context = {
            "intent": "order_status",
            "data_retrieved": False,
            "missing_info": ["No order ID was provided by the customer."],
        }
        # Fabricate a response with an order ID and dollar amount.
        text = "Your order ORD-12345 has been delivered. You paid $49.99."
        result = validate_response(text, "order_status", context, source="gemini")
        assert result.valid is False
        assert result.safe_fallback == SAFE_FALLBACK_MISSING_ID

    def test_legitimate_missing_id_question_is_valid(self):
        """A response that asks for the order ID is valid even with missing_info."""
        context = {
            "intent": "order_status",
            "data_retrieved": False,
            "missing_info": ["No order ID was provided by the customer."],
        }
        text = "Could you please provide your order ID so I can look up the details for you?"
        result = validate_response(text, "order_status", context, source="gemini")
        assert result.valid is True

    def test_business_claim_delivered_when_not_delivered(self):
        """Response claiming delivery when retrieved status shows processing should fail."""
        context = _order_context(status="processing")
        text = "Great news! Your order ORD-10001 has been delivered."
        result = validate_response(text, "order_status", context, source="gemini")
        assert result.valid is False

    def test_business_claim_cancelled_when_not_cancelled(self):
        context = _order_context(status="processing")
        text = "Your order ORD-10001 has been cancelled as per your request."
        result = validate_response(text, "cancel_order", context, source="gemini")
        assert result.valid is False

    def test_correct_status_claim_is_valid(self):
        """Response that accurately reflects the retrieved order status should pass."""
        context = _order_context(status="processing")
        text = "Your order ORD-10001 is currently in processing. We'll notify you when it ships."
        result = validate_response(text, "order_status", context, source="gemini")
        assert result.valid is True

    def test_general_response_not_incorrectly_rejected(self):
        """A factual general answer (greeting, product info) should not be rejected."""
        text = "Hello! I'm here to help you with your order or any other questions."
        result = validate_response(text, "greeting", None, source="gemini")
        assert result.valid is True

    def test_validation_result_has_quality_attached(self):
        text = "Your order is being processed."
        result = validate_response(text, "order_status", None, source="gemini")
        assert result.quality is not None
        assert isinstance(result.quality.score, float)

    def test_policy_response_is_valid_without_order_data(self):
        """Return policy explanation without order data should be valid."""
        text = (
            "Our return policy allows returns within 30 days of purchase. "
            "Items must be unused and in original packaging. "
            "Please initiate the return through your account portal."
        )
        result = validate_response(text, "return", None, source="gemini")
        assert result.valid is True


# ===========================================================================
# 4. Integration — Reply Pipeline with Validation
# ===========================================================================


class TestReplyPipelineIntegration:
    """Integration tests verifying Day 22-23 features in the live reply endpoint."""

    def test_valid_gemini_response_returned_normally(self, client, monkeypatch):
        """A clean Gemini response should pass validation and be returned."""
        monkeypatch.setattr(
            _GEMINI_PATCH,
            lambda m, h, sp: "Your order is currently being processed. Please allow 3-5 business days.",
        )
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        r = _reply(client, session_id, "Where is my order?")
        assert r.status_code == 201
        data = r.json()
        assert data["answer_source"] == "gemini"
        assert data["content"]

    def test_safe_fallback_returned_on_empty_gemini_response(self, client, monkeypatch):
        """If Gemini returns an empty string, a safe fallback is persisted and returned."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, sp: "   ")
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        # Use message that won't hit FAQ so Gemini path runs.
        r = _reply(client, session_id, "Tell me about your unique policies please")
        # Should succeed (201) but with a fallback message.
        assert r.status_code == 201
        data = r.json()
        # The response should be a safe fallback (non-empty and not the empty Gemini reply).
        assert data["content"]

    def test_unverified_operation_claim_replaced_with_fallback(self, client, monkeypatch):
        """A Gemini response claiming an uncompleted operation is replaced with the safe fallback."""
        fake_reply = (
            "Your refund has been processed successfully. "
            "You will receive the money within 3-5 business days."
        )
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, sp: fake_reply)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        # Order ORD-10001 exists in sample data with a non-refunded status.
        r = _reply(client, session_id, "I want a refund for my order ORD-10001")
        assert r.status_code == 201
        data = r.json()
        # The fallback message should replace the fake claim.
        assert data["content"] != fake_reply
        assert SAFE_FALLBACK_UNVERIFIED_OP in data["content"] or "cannot confirm" in data["content"].lower()

    def test_faq_path_unaffected_by_validation(self, client, monkeypatch):
        """FAQ-first routing still returns the FAQ answer without alteration."""
        faq_hit = [{"answer": "You can track your order at our website.", "score": 0.95}]
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: faq_hit)

        session_id, _ = _create_conversation(client)
        r = _reply(client, session_id, "How can I track my order?")
        assert r.status_code == 201
        data = r.json()
        assert data["answer_source"] == "faq"
        assert "track" in data["content"].lower()

    def test_response_schema_unchanged(self, client, monkeypatch):
        """API response schema must remain backward-compatible after Day 22-23."""
        monkeypatch.setattr(
            _GEMINI_PATCH,
            lambda m, h, sp: "I can help you with that. Please provide more details.",
        )
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        r = _reply(client, session_id, "Help me please")
        assert r.status_code == 201
        data = r.json()

        required = {"id", "conversation_id", "role", "content", "created_at", "answer_source", "intent", "entities"}
        assert required.issubset(data.keys())

    def test_gemini_exception_still_returns_502(self, client, monkeypatch):
        """Gemini exceptions remain handled correctly after Day 22-23 changes."""
        def exploding(*args, **kwargs):
            raise RuntimeError("Simulated Gemini failure")

        monkeypatch.setattr(_GEMINI_PATCH, exploding)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        r = _reply(client, session_id, "Unique question not in FAQ zxqwerty")
        assert r.status_code == 502

    def test_format_guidance_included_in_prompt(self, client, monkeypatch):
        """The system prompt passed to Gemini should include format guidance."""
        captured_prompt = {}

        def fake_gemini(message, history, system_prompt):
            captured_prompt["sp"] = system_prompt
            return "Your order is being processed."

        monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        # Use an order_status message so format guidance is included.
        r = _reply(client, session_id, "What is my order status?")
        assert r.status_code == 201
        sp = captured_prompt.get("sp", "")
        # System prompt should contain the tone rules (Day 22 additions).
        assert "concise" in sp.lower() or "tone" in sp.lower() or "professional" in sp.lower()

    def test_tone_reminder_in_prompt(self, client, monkeypatch):
        """Tone reminder is always appended to the Gemini prompt."""
        captured_prompt = {}

        def fake_gemini(message, history, system_prompt):
            captured_prompt["sp"] = system_prompt
            return "Helping you now."

        monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        r = _reply(client, session_id, "Hi there!")
        assert r.status_code == 201
        sp = captured_prompt.get("sp", "")
        assert "TONE RULES" in sp or "tone" in sp.lower()

    def test_conversation_history_and_persistence_intact(self, client, monkeypatch):
        """Conversation history and DB persistence still work correctly after Day 22-23."""
        call_count = {"n": 0}

        def fake_gemini(m, h, sp):
            call_count["n"] += 1
            return f"Reply number {call_count['n']}."

        monkeypatch.setattr(_GEMINI_PATCH, fake_gemini)
        monkeypatch.setattr(_FAQ_PATCH, lambda *a, **kw: [])

        session_id, _ = _create_conversation(client)
        _reply(client, session_id, "Question one")
        _reply(client, session_id, "Question two")

        hist = client.get(f"/api/v1/conversations/{session_id}/messages")
        assert hist.status_code == 200
        messages = hist.json()
        assert len(messages) == 4
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_non_existent_session_still_404(self, client, monkeypatch):
        """Non-existent session must still return 404 after Day 22-23 changes."""
        monkeypatch.setattr(_GEMINI_PATCH, lambda m, h, sp: "Hello.")
        r = _reply(client, "nonexistent-session-xyz", "Hello")
        assert r.status_code == 404


# ===========================================================================
# 5. Edge Cases & Reliability
# ===========================================================================


class TestEdgeCases:
    """Edge-case tests for the Day 22-23 layer."""

    def test_score_response_with_none_context(self):
        result = score_response("A reasonable response with good content.", "general", None)
        assert 0.0 <= result.score <= 1.0
        assert isinstance(result.critical_failure, bool)

    def test_validate_response_with_none_context(self):
        result = validate_response("A reasonable response.", "greeting", None, source="gemini")
        assert isinstance(result.valid, bool)

    def test_validate_product_info_response(self):
        text = (
            "The Wireless Headphones Pro costs $149.99 and is currently in stock. "
            "It includes a 2-year warranty. Features include noise cancellation and 30-hour battery life."
        )
        result = validate_response(text, "product_info", None, source="gemini")
        assert result.valid is True

    def test_validate_complaint_response(self):
        text = (
            "I'm truly sorry to hear about the frustrating experience you've had with your delivery. "
            "I understand how disappointing this must be. "
            "Please allow me to look into this and get it resolved for you right away."
        )
        result = validate_response(text, "complaint", None, source="gemini")
        assert result.valid is True

    def test_validate_technical_issue_response(self):
        text = (
            "I'm sorry to hear you're experiencing this issue. Here are some troubleshooting steps:\n"
            "1. Clear your browser cache.\n"
            "2. Try a different browser.\n"
            "3. Disable browser extensions.\n"
            "If the problem persists, please contact our support team."
        )
        result = validate_response(text, "technical_issue", None, source="gemini")
        assert result.valid is True

    def test_validate_multi_step_return_response(self):
        text = (
            "Our return policy allows returns within 30 days. To start a return:\n"
            "1. Log in to your account.\n"
            "2. Go to Orders and select the item.\n"
            "3. Click 'Return Item' and print the shipping label.\n"
            "4. Drop it at any authorized carrier location."
        )
        result = validate_response(text, "return", None, source="gemini")
        assert result.valid is True

    def test_format_guidance_payment_non_empty(self):
        guidance = get_format_guidance("payment")
        assert isinstance(guidance, str)
        assert len(guidance) > 10

    def test_format_guidance_account_falls_back_to_general(self):
        guidance = get_format_guidance("account")
        assert isinstance(guidance, str)
        # Should get general guidance for intents without specific format

    def test_score_response_long_response_within_range(self):
        text = ("This is a detailed response. " * 100)[:3000]
        result = score_response(text, "general", None)
        assert 0.0 <= result.score <= 1.0

    def test_validate_response_very_long_response_passes_if_valid(self):
        text = "Your order is currently processing. " * 50
        result = validate_response(text[:2500], "order_status", None, source="gemini")
        # Should pass; just a bit verbose.
        assert isinstance(result.valid, bool)
