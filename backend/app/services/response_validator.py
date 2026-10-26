"""Response validation service (Day 23).

Validates a candidate assistant response before it is returned to the
customer.  Validation is a *separate* concern from quality scoring:

- Quality scoring (response_quality.py) measures how good a response is.
- Validation (this module) checks whether it is *safe* to return it at all.

Validation checks
-----------------
1. Non-empty / non-malformed — the response is a usable string.
2. Critical quality gate — blocks responses with critical grounding failures.
3. Business-claim checks — for structured intents, verifies that factual
   claims in the response are consistent with retrieved records.
4. Missing-information check — when required identifiers are absent, the
   response must ask for them rather than fabricate data.

Fallback behaviour
------------------
When validation fails, the caller receives a ``ValidationResult`` with
``valid=False`` and a ``safe_fallback`` message that can be returned
directly to the customer.

The caller (main.py) controls whether to regenerate, use the fallback,
or propagate an error.  This module does NOT make that decision.

Safe fallbacks
--------------
``SAFE_FALLBACK_GENERIC``
    Used when no specific context is available.

``SAFE_FALLBACK_MISSING_ID``
    Used when a required order/tracking identifier is missing.

``SAFE_FALLBACK_GEMINI_ERROR``
    Used when Gemini fails to produce any response.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.response_quality import QualityResult, score_response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safe fallback strings
# ---------------------------------------------------------------------------

SAFE_FALLBACK_GENERIC = (
    "I'm sorry, I wasn't able to retrieve a reliable answer for your question. "
    "Could you please rephrase your request, or I can connect you with a human agent "
    "who will be happy to help."
)

SAFE_FALLBACK_MISSING_ID = (
    "To help you with this, I'll need your order ID or tracking number. "
    "Could you please provide it so I can look up the details for you?"
)

SAFE_FALLBACK_GEMINI_ERROR = (
    "I'm currently unable to generate a response. "
    "Please try again in a moment, or contact our support team directly for immediate assistance."
)

SAFE_FALLBACK_UNVERIFIED_OP = (
    "I can see your request, but I cannot confirm the outcome of this action without verified information. "
    "Please contact our support team directly to ensure this is handled correctly."
)

# ---------------------------------------------------------------------------
# Intents that require structured business data
# ---------------------------------------------------------------------------

# These intents *need* retrieved data to give a meaningful verified answer.
_DATA_REQUIRED_INTENTS = {
    "order_status",
    "shipping",
    "cancel_order",
    "refund",
    "return",
}

# These intents always need an order/tracking ID before data can be retrieved.
_ID_REQUIRED_INTENTS = {
    "order_status",
    "cancel_order",
    "refund",
    "return",
    "shipping",
}

# Patterns that suggest the model fabricated business-specific data.
_FABRICATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\border\s+(id|number|#)?\s*:?\s*(ORD|#)?[0-9]{4,}", re.IGNORECASE),
    re.compile(r"\btracking\s+(number|#)?\s*:?\s*(TRK|#)?[A-Z0-9]{6,}", re.IGNORECASE),
    re.compile(r"\bdelivered?\s+on\s+\w+\s+\d{1,2}", re.IGNORECASE),
    re.compile(r"\bexpected?\s+delivery\s+(date|by)\s+\w+\s+\d{1,2}", re.IGNORECASE),
    re.compile(r"\$\d+\.\d{2}\b"),  # Fabricated dollar amounts
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of response validation.

    Attributes
    ----------
    valid:
        True if the response passes all validation checks.
    safe_fallback:
        When ``valid=False``, a safe, user-friendly message to return instead.
        None when valid is True.
    failure_reasons:
        Human-readable list of reasons why validation failed.
    quality:
        The attached QualityResult from the scoring pass.
    """

    valid: bool
    safe_fallback: str | None
    failure_reasons: list[str] = field(default_factory=list)
    quality: QualityResult | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_response(
    response_text: str,
    intent: str,
    context: dict[str, Any] | None = None,
    source: str = "gemini",
) -> ValidationResult:
    """Validate a candidate response before returning it to the customer.

    Parameters
    ----------
    response_text:
        The raw candidate response string.
    intent:
        The classified intent for this turn.
    context:
        Business context dict from ``build_context()``.  Used to cross-check
        factual claims in the response.
    source:
        Either ``"faq"`` or ``"gemini"``.  FAQ responses skip most checks
        because they come from a curated, pre-verified dataset.

    Returns
    -------
    ValidationResult
        ``valid=True`` means the response is safe to return.
        ``valid=False`` means the caller should use ``safe_fallback``.
    """
    failure_reasons: list[str] = []

    # ------------------------------------------------------------------
    # Check 1: Non-empty / non-malformed
    # ------------------------------------------------------------------
    if not response_text or not response_text.strip():
        logger.warning("validate_response: empty response received (intent=%s, source=%s)", intent, source)
        return ValidationResult(
            valid=False,
            safe_fallback=SAFE_FALLBACK_GENERIC,
            failure_reasons=["Response is empty or whitespace-only."],
        )

    stripped = response_text.strip()

    # ------------------------------------------------------------------
    # FAQ responses: light-touch validation only.
    # ------------------------------------------------------------------
    if source == "faq":
        # FAQ answers are pre-verified; only reject genuinely empty ones.
        quality = score_response(stripped, intent, context)
        return ValidationResult(
            valid=True,
            safe_fallback=None,
            quality=quality,
        )

    # ------------------------------------------------------------------
    # Check 2: Quality scoring (Gemini responses)
    # ------------------------------------------------------------------
    quality = score_response(stripped, intent, context)

    if quality.critical_failure:
        logger.warning(
            "validate_response: CRITICAL quality failure (intent=%s, reasons=%s)",
            intent,
            quality.reasons,
        )
        return ValidationResult(
            valid=False,
            safe_fallback=SAFE_FALLBACK_UNVERIFIED_OP,
            failure_reasons=quality.reasons,
            quality=quality,
        )

    # ------------------------------------------------------------------
    # Check 3: Missing identifier — ID-required intents
    # ------------------------------------------------------------------
    if intent in _ID_REQUIRED_INTENTS and context is not None:
        missing_info = context.get("missing_info", [])
        no_order_id = any("No order ID" in m for m in missing_info)
        no_data = not context.get("data_retrieved")

        if no_data and no_order_id:
            # The response should ask for the ID, not fabricate an answer.
            has_fabricated = any(p.search(stripped) for p in _FABRICATION_PATTERNS)
            if has_fabricated:
                failure_reasons.append(
                    "Response appears to contain fabricated business data when no records were retrieved."
                )
                return ValidationResult(
                    valid=False,
                    safe_fallback=SAFE_FALLBACK_MISSING_ID,
                    failure_reasons=failure_reasons,
                    quality=quality,
                )

    # ------------------------------------------------------------------
    # Check 4: Business-claim consistency
    # ------------------------------------------------------------------
    if context is not None and context.get("data_retrieved"):
        claim_issues = _check_business_claims(stripped, context, intent)
        if claim_issues:
            for issue in claim_issues:
                logger.warning("validate_response: business-claim issue: %s (intent=%s)", issue, intent)
                failure_reasons.append(issue)
            # Business-claim failures are high-severity but not always critical.
            # If claims conflict with known data, fail validation.
            return ValidationResult(
                valid=False,
                safe_fallback=SAFE_FALLBACK_GENERIC,
                failure_reasons=failure_reasons,
                quality=quality,
            )

    # ------------------------------------------------------------------
    # Check 5: Low overall quality score (soft gate)
    # ------------------------------------------------------------------
    if not quality.passed:
        logger.info(
            "validate_response: low quality score %.3f (intent=%s, reasons=%s)",
            quality.score,
            intent,
            quality.reasons,
        )
        # Low quality alone doesn't force a fallback — log and pass.
        # The caller can decide based on the quality field if they want stricter behaviour.

    return ValidationResult(
        valid=True,
        safe_fallback=None,
        failure_reasons=failure_reasons,
        quality=quality,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_business_claims(
    response: str,
    context: dict[str, Any],
    intent: str,
) -> list[str]:
    """Check for specific business-data inconsistencies in the response.

    Returns a list of issue descriptions.  An empty list means no problems.

    This uses targeted pattern matching rather than keyword scanning alone,
    so it can distinguish a legitimate answer from an unsupported claim.
    """
    issues: list[str] = []

    order = context.get("order")
    shipment = context.get("shipment")

    # ------------------------------------------------------------------
    # Order status consistency
    # ------------------------------------------------------------------
    if order and intent in ("order_status", "cancel_order", "refund", "return"):
        verified_status = (order.get("status") or "").lower()
        order_id = (order.get("order_id") or "").upper()

        # Detect if the response claims the order is delivered when it isn't.
        if "delivered" not in verified_status:
            delivered_claim = re.search(
                r"\b(has been|was|is)\s+delivered\b",
                response,
                re.IGNORECASE,
            )
            if delivered_claim:
                issues.append(
                    f"Response claims order {order_id} was delivered, "
                    f"but retrieved status is '{verified_status}'."
                )

        # Detect if the response claims the order is cancelled when it isn't.
        if "cancel" not in verified_status:
            cancel_claim = re.search(
                r"\b(has been|was|is now)\s+(cancelled|canceled)\b",
                response,
                re.IGNORECASE,
            )
            if cancel_claim:
                issues.append(
                    f"Response claims order {order_id} was cancelled, "
                    f"but retrieved status is '{verified_status}'."
                )

    # ------------------------------------------------------------------
    # Shipment tracking consistency
    # ------------------------------------------------------------------
    if shipment and intent in ("order_status", "shipping"):
        verified_tracking = (shipment.get("tracking_number") or "").upper()

        # If the response cites a different tracking number, flag it.
        if verified_tracking:
            # Find any tracking-number-like strings in the response.
            found = re.findall(r"\b(TRK[-A-Z0-9]{4,})\b", response.upper())
            for candidate in found:
                if candidate != verified_tracking:
                    issues.append(
                        f"Response references tracking number {candidate} "
                        f"but retrieved record shows {verified_tracking}."
                    )

    return issues
