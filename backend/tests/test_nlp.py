"""Tests for NLP preprocessing and entity extraction modules."""

from fastapi.testclient import TestClient

from app.main import app
from app.nlp.entities import (
    ExtractedEntities,
    extract_amounts,
    extract_emails,
    extract_entities,
    extract_order_ids,
    extract_products,
    extract_tracking_numbers,
)
from app.nlp.preprocessing import (
    clean_text,
    expand_contractions,
    preprocess_text,
    tokenize,
)


def test_contraction_expansion():
    """Verify that common conversational contractions are expanded."""
    assert expand_contractions("I'm looking for help") == "i am looking for help"
    assert expand_contractions("can't cancel") == "cannot cancel"
    assert expand_contractions("won't arrive") == "will not arrive"
    assert expand_contractions("what's my order status") == "what is my order status"
    assert expand_contractions("where's my package") == "where is my package"
    assert expand_contractions("it's delayed") == "it is delayed"


def test_clean_text_normalizes_spaces_and_case():
    """Verify lowercasing and contiguous whitespace reduction."""
    raw = "   Where   is   MY   Order  #12345???   "
    cleaned = clean_text(raw)
    assert "where is my order #12345" in cleaned
    assert "   " not in cleaned


def test_tokenize_preserves_tokens_and_filters_stopwords():
    """Tokens must be lowercased and optionally stripped of stop words."""
    sentence = "How can I track my shipment?"
    tokens_all = tokenize(sentence, remove_stopwords=False)
    tokens_no_stop = tokenize(sentence, remove_stopwords=True)

    assert "track" in tokens_all
    assert "shipment" in tokens_all
    assert "how" in tokens_all

    assert "track" in tokens_no_stop
    assert "shipment" in tokens_no_stop
    assert "how" not in tokens_no_stop
    assert "can" not in tokens_no_stop
    assert "i" not in tokens_no_stop


def test_preprocess_text_output_structure():
    """preprocess_text must return consistent analysis structure."""
    res = preprocess_text("Where is my order #54321?")
    assert "raw" in res
    assert "normalized" in res
    assert "tokens" in res
    assert "tokens_no_stop" in res
    assert "char_count" in res
    assert "word_count" in res
    assert res["word_count"] > 0
    assert res["char_count"] > 0


def test_preprocess_empty_string():
    """Empty string preprocessing should yield safe default values."""
    res = preprocess_text("")
    assert res["char_count"] == 0
    assert res["word_count"] == 0
    assert res["tokens"] == []


def test_extract_order_ids_various_formats():
    """Order IDs in various common patterns should be extracted."""
    text1 = "I need help with order #12345 please"
    assert "12345" in extract_order_ids(text1)

    text2 = "Check ORD-987654 status"
    assert any("987654" in oid for oid in extract_order_ids(text2))

    text3 = "My order no. 445566 has not shipped"
    assert "445566" in extract_order_ids(text3)


def test_extract_emails():
    """Valid customer email addresses must be extracted."""
    text = "Send the confirmation to customer.support@example.com or user@test.co.uk"
    emails = extract_emails(text)
    assert len(emails) == 2
    assert "customer.support@example.com" in emails
    assert "user@test.co.uk" in emails


def test_extract_emails_deduplicates():
    """Identical emails mentioned multiple times must be deduplicated."""
    text = "Contact me at alice@example.com or ALICE@EXAMPLE.COM"
    emails = extract_emails(text)
    assert len(emails) == 1
    assert emails[0].lower() == "alice@example.com"


def test_extract_tracking_numbers():
    """Shipment tracking numbers must be extracted."""
    text1 = "Tracking number: TRK987654321"
    trks = extract_tracking_numbers(text1)
    assert any("987654321" in t for t in trks)

    text2 = "UPS tracking 1Z9999999999999999"
    assert "1Z9999999999999999" in extract_tracking_numbers(text2)


def test_extract_monetary_amounts():
    """Monetary amounts in various currencies must be captured."""
    text = "I was charged $49.99 instead of 50 USD and €25.00"
    amounts = extract_amounts(text)
    assert any("$49.99" in a for a in amounts)
    assert any("50 USD" in a for a in amounts)
    assert any("€25.00" in a for a in amounts)


def test_extract_products_catalog():
    """Catalog product mentions must be identified."""
    text = "I ordered a laptop and wireless headphones with a spare charger"
    products = extract_products(text)
    assert "laptop" in products
    assert "headphones" in products
    assert "charger" in products


def test_extract_entities_empty_input():
    """extract_entities on empty or unrelated text returns empty lists."""
    empty_res = extract_entities("")
    assert isinstance(empty_res, ExtractedEntities)
    assert not empty_res.has_any()

    unrelated_res = extract_entities("What a lovely sunny day")
    assert not unrelated_res.has_any()


def test_extract_entities_comprehensive():
    """Complex message with multiple entities is parsed completely."""
    text = "My order #889900 for a laptop was $999.00, tracking is TRK55667788, email me at john@example.com"
    entities = extract_entities(text)

    assert "889900" in entities.order_ids
    assert "laptop" in entities.products
    assert any("999" in a for a in entities.amounts)
    assert any("55667788" in t for t in entities.tracking_numbers)
    assert "john@example.com" in entities.emails
    assert entities.has_any()


def test_nlp_entities_api_endpoint(client):
    """POST /api/v1/nlp/entities should return extracted entities."""
    response = client.post(
        "/api/v1/nlp/entities",
        json={"message": "Order #443322 for a smartphone, email test@domain.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "443322" in data["order_ids"]
    assert "smartphone" in data["products"]
    assert "test@domain.com" in data["emails"]


def test_nlp_analyze_api_endpoint(client):
    """POST /api/v1/nlp/analyze should return full analysis payload."""
    response = client.post(
        "/api/v1/nlp/analyze",
        json={"message": "Where is my order #12345? Tracking link does not work."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "order_status"
    assert data["confidence"] > 0.5
    assert "12345" in data["entities"]["order_ids"]
    assert "order" in data["tokens"]
