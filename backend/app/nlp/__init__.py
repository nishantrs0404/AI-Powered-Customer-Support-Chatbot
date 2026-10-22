"""NLP package for customer support chatbot.

Exposes text preprocessing, intent classification, entity extraction,
and comprehensive message analysis.
"""

from typing import Any

from app.nlp.entities import ExtractedEntities, extract_entities
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
from app.nlp.preprocessing import clean_text, expand_contractions, preprocess_text, tokenize


def analyze_message(text: str) -> dict[str, Any]:
    """Perform complete NLP analysis on customer text.

    Returns normalized text, tokens, classified intent, confidence,
    and extracted entities.
    """
    preprocessed = preprocess_text(text)
    intent_res = classify_intent(text)
    entities = extract_entities(text)

    return {
        "text": text,
        "normalized": preprocessed["normalized"],
        "tokens": preprocessed["tokens"],
        "tokens_no_stop": preprocessed["tokens_no_stop"],
        "intent": intent_res.intent,
        "confidence": intent_res.confidence,
        "entities": entities.to_dict(),
        "is_confident": intent_res.confidence >= 0.5,
    }


__all__ = [
    "clean_text",
    "expand_contractions",
    "tokenize",
    "preprocess_text",
    "ExtractedEntities",
    "extract_entities",
    "IntentResult",
    "classify_intent",
    "analyze_message",
    "SUPPORTED_INTENTS",
    "GREETING",
    "ORDER_STATUS",
    "CANCEL_ORDER",
    "REFUND",
    "RETURN",
    "PAYMENT",
    "SHIPPING",
    "PRODUCT_INFO",
    "ACCOUNT",
    "TECHNICAL_ISSUE",
    "COMPLAINT",
    "HUMAN_AGENT",
    "UNKNOWN",
]
