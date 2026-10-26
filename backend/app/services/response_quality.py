"""Response quality scoring (Day 22).

Provides a lightweight, deterministic quality scoring layer that evaluates
assistant responses before they are returned to the customer.

Scoring dimensions
------------------
1. non_empty        — response has meaningful content            (weight 1)
2. length_ok        — response is within a reasonable length     (weight 1)
3. intent_relevant  — response references the expected topic     (weight 2)
4. grounded         — response uses retrieved business data      (weight 2)
5. no_filler        — response avoids known filler patterns      (weight 1)
6. no_unverified_op — response avoids unverified action claims   (weight 3)

The raw weighted score is normalised to [0.0, 1.0].

Critical failures
-----------------
Certain grounding failures are *critical* and override the overall score:
they force ``critical_failure=True`` regardless of how well the response
scores on other dimensions.  A critical failure must be handled by the
validator (see ``response_validator.py``) independently of the overall score.

Thresholds
----------
QUALITY_THRESHOLD : float
    Responses scoring below this are considered low quality.  The reply
    pipeline may choose to use a safe fallback instead.  Default 0.5.

CRITICAL_FAILURE_THRESHOLD : float
    Not a score — if ``critical_failure`` is True the response must be
    treated as failed regardless of the numeric score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUALITY_THRESHOLD = 0.5  # Below this → low quality; fallback preferred.

# Patterns that indicate unverified operation claims.
_UNVERIFIED_OP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(refund|reimbursement)\s+(has been|was|is now|has been processed|processed)\b", re.IGNORECASE),
    re.compile(r"\b(cancellation|order)\s+(has been|was|is now)\s+(cancelled|canceled|confirmed)\b", re.IGNORECASE),
    re.compile(r"\breturn\s+(has been|was|is now)\s+(approved|processed|completed)\b", re.IGNORECASE),
    re.compile(r"\b(your\s+)?(order|shipment)\s+(has been|was)\s+(shipped|dispatched|delivered)\b", re.IGNORECASE),
    re.compile(r"\b(i have|we have|i've|we've)\s+(cancelled|canceled|refunded|processed)\b", re.IGNORECASE),
    re.compile(r"\byou\s+will\s+receive\s+(your\s+)?(refund|money|reimbursement)\s+within\b", re.IGNORECASE),
]

# Known filler phrases to penalise.
_FILLER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bthank you for (your|reaching out|contacting|getting in touch)\b", re.IGNORECASE),
    re.compile(r"\bwe (value|appreciate) your (business|patience|feedback|understanding)\b", re.IGNORECASE),
    re.compile(r"\bi (sincerely )?(apologize|apologise|am sorry) for (the|any|your)\b", re.IGNORECASE),
    re.compile(r"\bplease (do not hesitate|feel free) to (contact|reach out)\b", re.IGNORECASE),
    re.compile(r"\bhave a (great|wonderful|nice|good) (day|evening|rest)\b", re.IGNORECASE),
    re.compile(r"\bhappy to (help|assist) (you )?(today|here|with that)\b", re.IGNORECASE),
]

# Keywords that suggest the response is on-topic for common intents.
_INTENT_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "order_status":    ["order", "status", "track", "shipment", "delivery", "shipped", "package"],
    "shipping":        ["ship", "delivery", "carrier", "track", "dispatch", "estimated"],
    "return":          ["return", "policy", "window", "label", "exchange", "process"],
    "refund":          ["refund", "money", "reimburs", "credit", "process", "timeline"],
    "cancel_order":    ["cancel", "cancellation", "policy", "order"],
    "technical_issue": ["issue", "error", "bug", "try", "step", "browser", "clear", "reload", "contact"],
    "complaint":       ["apologize", "apologise", "sorry", "understand", "concern", "address"],
    "product_info":    ["product", "price", "stock", "warranty", "feature", "description"],
    "payment":         ["payment", "charge", "card", "billing", "invoice", "bank"],
    "account":         ["account", "password", "login", "email", "reset", "profile"],
    "human_agent":     ["agent", "human", "representative", "connect", "transfer"],
    "greeting":        ["hello", "hi", "help", "assist", "welcome"],
}

# Responses that are far too short or far too long are penalised.
_MIN_RESPONSE_CHARS = 20
_MAX_RESPONSE_CHARS = 3000


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class QualityResult:
    """Outcome of the quality scoring pass.

    Attributes
    ----------
    score:
        Weighted score in [0.0, 1.0].  Higher is better.
    passed:
        True if score >= QUALITY_THRESHOLD and no critical failure.
    critical_failure:
        True when a grounding rule has been violated regardless of score.
    reasons:
        Human-readable list of reasons for any deductions or failures.
    dimension_scores:
        Individual score per dimension for diagnostics.
    """

    score: float
    passed: bool
    critical_failure: bool
    reasons: list[str] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_response(
    response_text: str,
    intent: str,
    context: dict[str, Any] | None = None,
) -> QualityResult:
    """Score a candidate response on multiple quality dimensions.

    Parameters
    ----------
    response_text:
        The raw text of the assistant's candidate response.
    intent:
        The classified intent for this turn.
    context:
        The business context dict from ``build_context()``.  Used to verify
        whether the response is grounded in retrieved data.

    Returns
    -------
    QualityResult
        Scored result with pass/fail and per-dimension breakdown.

    Notes
    -----
    This function is deterministic — identical inputs always return the same
    result.  It never calls external APIs.
    """
    reasons: list[str] = []
    dim: dict[str, float] = {}
    critical_failure = False

    # ------------------------------------------------------------------
    # D1: Non-empty check  (weight 1)
    # ------------------------------------------------------------------
    stripped = response_text.strip() if response_text else ""
    if len(stripped) >= _MIN_RESPONSE_CHARS:
        dim["non_empty"] = 1.0
    else:
        dim["non_empty"] = 0.0
        reasons.append("Response is empty or too short.")

    # ------------------------------------------------------------------
    # D2: Length within bounds  (weight 1)
    # ------------------------------------------------------------------
    if _MIN_RESPONSE_CHARS <= len(stripped) <= _MAX_RESPONSE_CHARS:
        dim["length_ok"] = 1.0
    elif len(stripped) > _MAX_RESPONSE_CHARS:
        dim["length_ok"] = 0.5
        reasons.append("Response is unusually long.")
    else:
        dim["length_ok"] = 0.0

    # ------------------------------------------------------------------
    # D3: Intent relevance  (weight 2)
    # ------------------------------------------------------------------
    keywords = _INTENT_TOPIC_KEYWORDS.get(intent, [])
    if not keywords or intent in ("unknown",):
        # No keywords for this intent — give full credit.
        dim["intent_relevant"] = 1.0
    else:
        lower = stripped.lower()
        matched = sum(1 for kw in keywords if kw in lower)
        ratio = matched / len(keywords)
        dim["intent_relevant"] = min(1.0, ratio * 2.5)  # generous scaling
        if dim["intent_relevant"] < 0.2:
            reasons.append(f"Response appears off-topic for intent '{intent}'.")

    # ------------------------------------------------------------------
    # D4: Grounding in retrieved data  (weight 2)
    # ------------------------------------------------------------------
    if context is None or not context.get("data_retrieved"):
        # No data was expected — grounding is N/A; full credit.
        dim["grounded"] = 1.0
    else:
        # Data was retrieved. Check if the response is coherent with it.
        # We use lightweight heuristics rather than semantic comparison.
        order = context.get("order")
        shipment = context.get("shipment")
        product = context.get("product")

        grounding_ok = True

        if order:
            order_id = (order.get("order_id") or "").upper()
            if order_id and order_id not in stripped.upper():
                # The response should reference the order ID when data is available.
                # Allow soft failure — not critical by itself.
                grounding_ok = False
                reasons.append(f"Response may not reference the retrieved order ({order_id}).")

        if grounding_ok:
            dim["grounded"] = 1.0
        else:
            dim["grounded"] = 0.6  # Soft penalty; may still pass threshold.

    # ------------------------------------------------------------------
    # D5: Absence of filler  (weight 1)
    # ------------------------------------------------------------------
    filler_hits = sum(1 for p in _FILLER_PATTERNS if p.search(stripped))
    if filler_hits == 0:
        dim["no_filler"] = 1.0
    elif filler_hits == 1:
        dim["no_filler"] = 0.7
        reasons.append("Response contains a filler phrase.")
    else:
        dim["no_filler"] = 0.4
        reasons.append(f"Response contains {filler_hits} filler phrases.")

    # ------------------------------------------------------------------
    # D6: No unverified operation claims  (weight 3) — CRITICAL
    # ------------------------------------------------------------------
    # Check only when the intent involves a state-changing operation AND
    # no confirmed completion is present in the retrieved context.
    _transactional_intents = {"refund", "return", "cancel_order"}
    if intent in _transactional_intents:
        unverified_hits = [p.pattern for p in _UNVERIFIED_OP_PATTERNS if p.search(stripped)]
        if unverified_hits:
            # Determine whether the retrieved data confirms the operation.
            context_confirms = _context_confirms_operation(intent, context)
            if not context_confirms:
                dim["no_unverified_op"] = 0.0
                critical_failure = True
                reasons.append(
                    "CRITICAL: Response claims an operation completed without evidence in retrieved data."
                )
            else:
                dim["no_unverified_op"] = 1.0
        else:
            dim["no_unverified_op"] = 1.0
    else:
        # For non-transactional intents, still flag obvious false claims.
        unverified_hits = [p.pattern for p in _UNVERIFIED_OP_PATTERNS if p.search(stripped)]
        if unverified_hits:
            context_confirms = _context_confirms_operation(intent, context)
            if not context_confirms:
                dim["no_unverified_op"] = 0.0
                critical_failure = True
                reasons.append(
                    "CRITICAL: Response contains unverified operation claims."
                )
            else:
                dim["no_unverified_op"] = 1.0
        else:
            dim["no_unverified_op"] = 1.0

    # ------------------------------------------------------------------
    # Weighted aggregation
    # ------------------------------------------------------------------
    weights = {
        "non_empty":        3,  # Heavy weight — an empty response is fundamentally unusable.
        "length_ok":        2,  # Short/malformed responses are also very low quality.
        "intent_relevant":  2,
        "grounded":         2,
        "no_filler":        1,
        "no_unverified_op": 3,
    }

    total_weight = sum(weights.values())
    weighted_sum = sum(dim.get(d, 0.0) * w for d, w in weights.items())
    score = round(weighted_sum / total_weight, 4)

    # A critical failure overrides pass/fail regardless of numeric score.
    passed = (score >= QUALITY_THRESHOLD) and not critical_failure

    return QualityResult(
        score=score,
        passed=passed,
        critical_failure=critical_failure,
        reasons=reasons,
        dimension_scores=dim,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _context_confirms_operation(intent: str, context: dict[str, Any] | None) -> bool:
    """Return True if retrieved data explicitly confirms the operation outcome.

    This is a conservative check — we only return True when the data contains
    explicit evidence that the operation is done.  When in doubt, return False.
    """
    if context is None:
        return False

    order = context.get("order")
    if order is None:
        return False

    status = (order.get("status") or "").lower()

    if intent == "cancel_order" and "cancel" in status:
        return True
    if intent == "refund" and ("refund" in status or "reimburs" in status):
        return True
    if intent == "return" and "return" in status:
        return True

    return False
