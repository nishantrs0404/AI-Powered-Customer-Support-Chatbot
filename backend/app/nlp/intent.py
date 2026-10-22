"""Intent recognition engine for customer support chatbot.

Implements rule-based and keyword-weighted intent classification supporting
all 13 customer support intents defined in FR-04.
"""

import re
from typing import Any
from pydantic import BaseModel, Field

from app.nlp.preprocessing import clean_text, tokenize


# All 13 supported intents defined in requirements FR-04
GREETING = "greeting"
ORDER_STATUS = "order_status"
CANCEL_ORDER = "cancel_order"
REFUND = "refund"
RETURN = "return"
PAYMENT = "payment"
SHIPPING = "shipping"
PRODUCT_INFO = "product_info"
ACCOUNT = "account"
TECHNICAL_ISSUE = "technical_issue"
COMPLAINT = "complaint"
HUMAN_AGENT = "human_agent"
UNKNOWN = "unknown"

SUPPORTED_INTENTS = [
    GREETING,
    ORDER_STATUS,
    CANCEL_ORDER,
    REFUND,
    RETURN,
    PAYMENT,
    SHIPPING,
    PRODUCT_INFO,
    ACCOUNT,
    TECHNICAL_ISSUE,
    COMPLAINT,
    HUMAN_AGENT,
    UNKNOWN,
]

INTENT_CONFIDENCE_THRESHOLD = 0.35


class IntentResult(BaseModel):
    """Result of intent classification."""

    intent: str = Field(description="Detected intent name")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence score")
    matched_keywords: list[str] = Field(default_factory=list, description="Keywords contributing to score")
    matched_patterns: list[str] = Field(default_factory=list, description="Regex patterns matched")
    scores: dict[str, float] = Field(default_factory=dict, description="Calculated scores per intent")


# High-confidence intent regular expressions
INTENT_PATTERNS: dict[str, list[str]] = {
    HUMAN_AGENT: [
        r"\b(speak|talk|connect|transfer)\s+(to|with)\s+(a\s+|an\s+|the\s+)?(human|agent|person|representative|operator|advisor|someone|customer\s+support|live\s+support|real\s+person)\b",
        r"\b(transfer|escalate)\s+(me\s+)?(to\s+)?(a\s+)?(human|agent|representative|supervisor|manager|customer\s+support|tier\s+2)\b",
        r"\b(want|need|get)\s+(a\s+)?(human|live\s+agent|representative|real\s+person)\b",
        r"\b(human\s+support|live\s+agent|customer\s+service\s+rep|real\s+person)\b",
        r"\b(connect|transfer)\s+me\s+(with|to)\s+(live\s+|an?\s+)?(support|agent|person|representative)\b",
        r"\bcan\s+i\s+talk\s+to\s+a\s+(real\s+)?person\b",
        r"\bescalat(e|ion)\s+this\s+to\s+a\s+human\b",
    ],
    CANCEL_ORDER: [
        r"\b(cancel|stop|abort|void)\s+(my\s+|the\s+|this\s+)?(order|purchase|shipment)\b",
        r"\bhow\s+(can\s+i|to)\s+cancel\s+(my\s+)?order\b",
        r"\bwant\s+to\s+cancel\s+(my\s+)?order\b",
        r"\bneed\s+to\s+cancel\s+(my\s+)?order\b",
        r"\bcan\s+i\s+cancel\s+(my\s+)?order\b",
        r"\bcancel\s+order\s+#?[a-z0-9_-]+\b",
    ],
    ORDER_STATUS: [
        r"\b(where\s+is|track|status\s+of|check)\s+(my\s+|the\s+)?(order|package|shipment|delivery|parcel)\b",
        r"\b(track|check)\s+(my\s+)?(shipment|delivery|order)\b",
        r"\bwhere\s+did\s+my\s+order\s+go\b",
        r"\bhas\s+my\s+order\s+shipped\b",
        r"\border\s+(tracking|status|update|progress)\b",
        r"\btrack\s+(my\s+)?(order|package)\b",
        r"\btrack\s+#?[0-9a-z_-]{4,}\b",
    ],
    REFUND: [
        r"\b(request|get|want|claim|demand|need)\s+(a\s+)?refund\b",
        r"\b(where|when)\s+is\s+my\s+refund\b",
        r"\b(when\s+will|how\s+long\s+for)\s+(my\s+|a\s+)?refund\b",
        r"\b(money\s+back|get\s+my\s+money\s+back)\b",
        r"\brefund\s+(for\s+my\s+item|status|policy|process|timeline|money|payment|order|not\s+arrived)\b",
        r"\brefund\s+my\s+(money|payment|order)\b",
    ],
    RETURN: [
        r"\b(how\s+to\s+|how\s+do\s+i\s+)?return\s+(an?\s+|my\s+|this\s+)?(item|product|order|package|goods)\b",
        r"\breturn\s+(policy|window|label|instructions|process|period|shipping\s+label)\b",
        r"\bsend\s+back\s+(an?\s+|my\s+|this\s+|the\s+)?(item|product|order)\b",
        r"\bexchange\s+(an?\s+|my\s+|this\s+)?(item|product|size|order)\b",
    ],
    GREETING: [
        r"^(hello|hi|hey|good\s+(morning|afternoon|evening)|howdy|greetings|hola)\b",
        r"^hi\s+(there|bot|support|assistant)\b",
        r"^hey\s+there\b",
    ],
    PAYMENT: [
        r"\b(payment|credit\s+card|debit\s+card|paypal|apple\s+pay|billing)\s+(was\s+|got\s+)?(declined|failed|rejected|error|problem|issue)\b",
        r"\b(charged\s+twice|double\s+charge|duplicate\s+charge|overcharged)\b",
        r"\b(how\s+to\s+pay|payment\s+methods?|accepted\s+payments?|pay\s+by\s+card)\b",
        r"\b(invoice|receipt|invoice\s+for\s+my\s+payment|get\s+an\s+invoice)\b",
    ],
    SHIPPING: [
        r"\b(how\s+long\s+does\s+delivery\s+take|delivery\s+time|shipping\s+time|estimated\s+delivery)\b",
        r"\b(shipping\s+fee|shipping\s+fees|shipping\s+cost|shipping\s+costs|delivery\s+charge|free\s+shipping)\b",
        r"\b(international\s+shipping|ship\s+internationally|do\s+you\s+ship|offer\s+international\s+shipping)\b",
        r"\b(customs|import\s+duty|shipping\s+carrier|express\s+delivery)\b",
    ],
    PRODUCT_INFO: [
        r"\b(product\s+information|product\s+details|specifications|specs|size\s+guide)\b",
        r"\b(is\s+it\s+in\s+stock|currently\s+in\s+stock|in\s+stock|availability)\b",
        r"\bwarranty\s+(period|coverage|details|info)\b",
        r"\b(user\s+manual|compatibility|dimensions|materials?|features)\b",
    ],
    ACCOUNT: [
        r"\b(reset|change|forgot)\s+(my\s+)?password\b",
        r"\b(cannot|can'?t|unable\s+to)\s+(log\s+in|login|sign\s+in)\b",
        r"\b(login|log\s+in|sign\s+in)\s+(issue|problem|failed|error)\b",
        r"\b(change|update)\s+(my\s+)?(account\s+email|email|password|profile|address)\b",
        r"\b(delete|close|deactivate)\s+(my\s+)?account\b",
        r"\bcannot\s+access\s+my\s+account\b",
    ],
    TECHNICAL_ISSUE: [
        r"\b(website|app|page|site|checkout)\s+(crashed|not\s+working|broken|down|frozen|glitched)\b",
        r"\b(frozen\s+and\s+not\s+working|crashed\s+during\s+checkout)\b",
        r"\b(bug|error\s+code\s+[0-9]+|technical\s+issue|500\s+error|error\s+code\s+500|404\s+error)\b",
        r"\b(button\s+not\s+clicking|page\s+won'?t\s+load|cart\s+is\s+empty)\b",
        r"\bpromo\s+code\s+(is\s+)?(not\s+working|invalid|error)\b",
    ],
    COMPLAINT: [
        r"\b(file|submit|make|register)\s+(a\s+)?(formal\s+)?complaint\b",
        r"\b(terrible|horrible|awful|unacceptable|worst|disgraceful)\s+(customer\s+service|service|support|experience|product|delay)\b",
        r"\b(very\s+disappointed|extremely\s+unhappy|furious|fed\s+up)\b",
        r"\bwant\s+to\s+speak\s+with\s+a\s+manager\b",
        r"\bthreaten\s+(legal|consumer\s+protection)\b",
    ],
}


# Keyword dictionary for token-overlap scoring
INTENT_KEYWORDS: dict[str, list[str]] = {
    HUMAN_AGENT: ["human", "agent", "representative", "person", "operator", "advisor", "escalate", "supervisor", "manager"],
    CANCEL_ORDER: ["cancel", "cancellation", "abort", "void", "stop"],
    ORDER_STATUS: ["track", "tracking", "status", "where", "package", "shipment", "shipped", "arrived", "delivery"],
    REFUND: ["refund", "refunds", "reimbursement", "money"],
    RETURN: ["return", "returns", "exchange", "label", "replacement"],
    GREETING: ["hello", "hi", "hey", "greetings", "morning", "afternoon", "evening", "howdy"],
    PAYMENT: ["payment", "pay", "card", "billing", "invoice", "receipt", "charge", "charged", "declined"],
    SHIPPING: ["shipping", "ship", "delivery", "carrier", "international", "customs", "freight", "postage"],
    PRODUCT_INFO: ["product", "specifications", "warranty", "manual", "features", "stock", "details", "compatible"],
    ACCOUNT: ["password", "login", "account", "profile", "username", "email", "reset", "deactivate"],
    TECHNICAL_ISSUE: ["bug", "crash", "crashed", "glitch", "error", "broken", "freeze", "frozen", "down", "promo"],
    COMPLAINT: ["complaint", "terrible", "horrible", "unacceptable", "disappointed", "worst", "unhappy", "angry", "poor"],
}


def classify_intent(text: str) -> IntentResult:
    """Classify the intent of a customer message using patterns and keyword weights."""
    if not text or not text.strip():
        return IntentResult(
            intent=UNKNOWN,
            confidence=0.0,
            matched_keywords=[],
            matched_patterns=[],
            scores={intent: 0.0 for intent in SUPPORTED_INTENTS},
        )

    cleaned = clean_text(text)
    tokens = set(tokenize(text, remove_stopwords=True))

    scores: dict[str, float] = {intent: 0.0 for intent in SUPPORTED_INTENTS}
    matched_patterns_by_intent: dict[str, list[str]] = {intent: [] for intent in SUPPORTED_INTENTS}
    matched_keywords_by_intent: dict[str, list[str]] = {intent: [] for intent in SUPPORTED_INTENTS}

    # Step 1: Check high-confidence regex patterns
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, cleaned, flags=re.IGNORECASE):
                matched_patterns_by_intent[intent].append(pattern)
                scores[intent] = max(scores[intent], 0.92)

    # Step 2: Calculate token-keyword overlap score
    for intent, keywords in INTENT_KEYWORDS.items():
        overlap = [kw for kw in keywords if kw in tokens or re.search(rf"\b{re.escape(kw)}\b", cleaned)]
        if overlap:
            matched_keywords_by_intent[intent].extend(overlap)
            # 1 keyword -> 0.50, 2 keywords -> 0.70, 3+ keywords -> 0.85
            overlap_score = min(0.85, 0.35 + (0.18 * len(overlap)))
            scores[intent] = max(scores[intent], overlap_score)

    # Step 3: Domain-specific disambiguation rules
    # - "cancel my order" should firmly favor CANCEL_ORDER over ORDER_STATUS
    if scores[CANCEL_ORDER] > 0.4 and scores[ORDER_STATUS] > 0.4:
        if re.search(r"\bcancel\b", cleaned):
            scores[CANCEL_ORDER] = max(scores[CANCEL_ORDER], 0.95)
            scores[ORDER_STATUS] = min(scores[ORDER_STATUS], 0.40)

    # - Explicit human agent requests take high priority
    if matched_patterns_by_intent[HUMAN_AGENT]:
        scores[HUMAN_AGENT] = 0.98

    # - Pure greeting like "hello" shouldn't trigger other intents
    if re.fullmatch(r"^(hello|hi|hey|good\s+(morning|afternoon|evening)|howdy)\b.*", cleaned) and len(tokens) <= 2:
        scores[GREETING] = 0.95

    # Find highest scoring intent
    best_intent = UNKNOWN
    best_score = 0.0

    for intent, score in scores.items():
        if intent == UNKNOWN:
            continue
        if score > best_score:
            best_score = score
            best_intent = intent

    # Check if confidence threshold is met
    if best_score < INTENT_CONFIDENCE_THRESHOLD:
        best_intent = UNKNOWN
        best_score = round(best_score, 4)

    return IntentResult(
        intent=best_intent,
        confidence=round(best_score, 4),
        matched_keywords=list(dict.fromkeys(matched_keywords_by_intent.get(best_intent, []))),
        matched_patterns=matched_patterns_by_intent.get(best_intent, []),
        scores={k: round(v, 4) for k, v in scores.items()},
    )
