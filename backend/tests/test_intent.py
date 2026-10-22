"""Tests for intent recognition engine covering all 13 customer support intents."""

import pytest
from app.nlp.intent import (
    ACCOUNT,
    CANCEL_ORDER,
    COMPLAINT,
    GREETING,
    HUMAN_AGENT,
    ORDER_STATUS,
    PAYMENT,
    PRODUCT_INFO,
    REFUND,
    RETURN,
    SHIPPING,
    SUPPORTED_INTENTS,
    TECHNICAL_ISSUE,
    UNKNOWN,
    IntentResult,
    classify_intent,
)


def test_supported_intents_count_and_completeness():
    """All 13 intents from FR-04 must be present in SUPPORTED_INTENTS."""
    assert len(SUPPORTED_INTENTS) == 13
    expected_intents = {
        "greeting",
        "order_status",
        "cancel_order",
        "refund",
        "return",
        "payment",
        "shipping",
        "product_info",
        "account",
        "technical_issue",
        "complaint",
        "human_agent",
        "unknown",
    }
    assert set(SUPPORTED_INTENTS) == expected_intents


def test_classify_greeting_intent():
    """Greetings should be classified as greeting with high confidence."""
    for phrase in ["Hello", "Hi there", "Good morning", "Hey bot"]:
        result = classify_intent(phrase)
        assert result.intent == GREETING
        assert result.confidence >= 0.70


def test_classify_order_status_intent():
    """Order status questions should be classified correctly."""
    phrases = [
        "Where is my order #12345?",
        "Can you track my shipment?",
        "Has my order shipped yet?",
        "Check my order status please",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == ORDER_STATUS
        assert result.confidence >= 0.70


def test_classify_cancel_order_intent():
    """Order cancellation requests must be identified."""
    phrases = [
        "I need to cancel my order",
        "Cancel order #998877",
        "Please abort my purchase",
        "Can I cancel my order before it ships?",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == CANCEL_ORDER
        assert result.confidence >= 0.80


def test_classify_refund_intent():
    """Refund inquiries should map to refund intent."""
    phrases = [
        "I want a refund for my item",
        "When will my refund arrive?",
        "Where is my refund money?",
        "Can I get my money back?",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == REFUND
        assert result.confidence >= 0.70


def test_classify_return_intent():
    """Return requests must be recognized."""
    phrases = [
        "How do I return this product?",
        "What is your return policy?",
        "I need a return shipping label",
        "Can I send back this item for an exchange?",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == RETURN
        assert result.confidence >= 0.70


def test_classify_payment_intent():
    """Payment and billing queries should be detected."""
    phrases = [
        "My credit card payment was declined",
        "I was charged twice for one item",
        "What payment methods do you accept?",
        "Can I get an invoice for my payment?",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == PAYMENT
        assert result.confidence >= 0.70


def test_classify_shipping_intent():
    """Delivery and shipping queries must be identified."""
    phrases = [
        "How long does delivery take?",
        "Do you offer international shipping?",
        "How much are the shipping fees?",
        "What is the estimated delivery time?",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == SHIPPING
        assert result.confidence >= 0.70


def test_classify_product_info_intent():
    """Product specifications and inventory questions."""
    phrases = [
        "What are the specifications of this laptop?",
        "Is this product currently in stock?",
        "What is the warranty coverage for this phone?",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == PRODUCT_INFO
        assert result.confidence >= 0.70


def test_classify_account_intent():
    """Account management and credential questions."""
    phrases = [
        "I forgot my password and need to reset it",
        "I cannot log in to my account",
        "How can I change my account email?",
        "Please delete my account",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == ACCOUNT
        assert result.confidence >= 0.70


def test_classify_technical_issue_intent():
    """System, application, and checkout bugs."""
    phrases = [
        "The website crashed during checkout",
        "The app is completely frozen and not working",
        "I keep getting an error code 500",
        "My promo code is not working at payment",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == TECHNICAL_ISSUE
        assert result.confidence >= 0.70


def test_classify_complaint_intent():
    """Strong dissatisfaction and formal complaints."""
    phrases = [
        "I want to file a formal complaint",
        "This is the worst customer service ever, unacceptable delay",
        "I am very disappointed with the terrible service",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == COMPLAINT
        assert result.confidence >= 0.70


def test_classify_human_agent_intent():
    """Direct requests to reach a human support representative."""
    phrases = [
        "I want to speak to a human agent",
        "Can I talk to a real person?",
        "Transfer me to customer support representative",
        "Connect me with live support",
        "Escalate this to a human manager",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == HUMAN_AGENT
        assert result.confidence >= 0.85


def test_classify_unknown_intent():
    """Gibberish or completely out-of-domain queries return unknown."""
    phrases = [
        "quantum entanglement and general relativity",
        "blablabla xyz123 foo bar",
        "the capital of France is Paris",
    ]
    for phrase in phrases:
        result = classify_intent(phrase)
        assert result.intent == UNKNOWN


def test_classify_empty_string_returns_unknown():
    """Empty or whitespace input must return unknown with 0.0 confidence."""
    res1 = classify_intent("")
    assert res1.intent == UNKNOWN
    assert res1.confidence == 0.0

    res2 = classify_intent("    ")
    assert res2.intent == UNKNOWN
    assert res2.confidence == 0.0


def test_disambiguation_cancel_vs_status():
    """'cancel my order' must disambiguate to CANCEL_ORDER over ORDER_STATUS."""
    result = classify_intent("Please cancel my order #12345")
    assert result.intent == CANCEL_ORDER
    assert result.confidence >= 0.80


def test_disambiguation_human_agent_priority():
    """Human agent request takes high precedence even when other keywords are present."""
    result = classify_intent("I need to speak to a human agent about my delayed order")
    assert result.intent == HUMAN_AGENT
    assert result.confidence >= 0.85


def test_intent_result_scores_structure():
    """IntentResult must contain scores for all supported intents bounded [0, 1]."""
    result = classify_intent("Where is my order?")
    assert isinstance(result, IntentResult)
    for intent_name in SUPPORTED_INTENTS:
        assert intent_name in result.scores
        score = result.scores[intent_name]
        assert 0.0 <= score <= 1.0


def test_nlp_intent_api_endpoint(client):
    """POST /api/v1/nlp/intent endpoint returns IntentResponse."""
    response = client.post(
        "/api/v1/nlp/intent",
        json={"message": "I would like to speak to a human representative"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == HUMAN_AGENT
    assert data["confidence"] >= 0.85
    assert isinstance(data["matched_keywords"], list)
    assert isinstance(data["matched_patterns"], list)


def test_reply_endpoint_includes_intent_and_entities(client, monkeypatch):
    """POST /api/v1/conversations/{id}/reply populates intent and entities in ReplyResponse."""
    # Mock FAQ to return hit so we don't call Gemini
    session_response = client.post("/api/v1/conversations")
    session_id = session_response.json()["session_id"]

    reply_response = client.post(
        f"/api/v1/conversations/{session_id}/reply",
        json={"message": "Where is my order #554433?"},
    )
    assert reply_response.status_code == 201
    data = reply_response.json()

    assert "intent" in data
    assert data["intent"] == ORDER_STATUS
    assert "entities" in data
    assert "554433" in data["entities"]["order_ids"]
