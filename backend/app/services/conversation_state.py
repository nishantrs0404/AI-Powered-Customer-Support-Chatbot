"""Conversational state tracking service (Day 21).

Implements multi-turn slot filling so the chatbot can resolve follow-up
references (e.g. "its tracking", "that order") from earlier turns without
the customer repeating identifiers every message.

Design principles
-----------------
- State is persisted in SQLite via the ``ConversationState`` model so it
  survives service restarts.
- Each conversation session has at most **one** state row (upsert pattern).
- Only a single ``active_order_id`` and ``active_tracking_number`` are
  tracked — the "most recently confirmed" values for the session.
- Multiple conflicting identifiers in a single message trigger a
  clarification request instead of silently picking one.
- State is cleared or overwritten when the customer changes topic or
  provides a new identifier — never silently stale.
- Intents classified as off-topic (greeting, account, technical_issue,
  payment, complaint) wipe order/tracking slots because the context has
  changed.  The ``unknown`` intent is intentionally *neutral* — it does
  not clear slots (the customer may have just typed a bare ID as a
  follow-up).

Public API
----------
``load_state(conversation_id, db)``
    Return the existing state row or ``None``.

``resolve_entities(current_entities, intent, state)``
    Merge the current-turn entities with slot memory; return a merged
    entity dict plus an ``ambiguous`` flag.

``update_state(conversation_id, intent, entities, ambiguous, db)``
    Upsert the state row with the latest turn's resolved values.

``build_clarification_reply()``
    Return a canned clarification message for the ambiguous-IDs case.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

# ---------------------------------------------------------------------------
# Intent categories that control slot lifetime
# ---------------------------------------------------------------------------

# Intents where order/tracking context is meaningful.
_ORDER_BEARING_INTENTS = {
    "order_status",
    "cancel_order",
    "refund",
    "return",
    "shipping",
}

# Intents that should **reset** order/tracking slots because the topic has
# clearly changed away from order management.
_TOPIC_CHANGE_INTENTS = {
    "greeting",
    "account",
    "technical_issue",
    "payment",
    "complaint",
    "product_info",
    "human_agent",
}


# ---------------------------------------------------------------------------
# Low-level DB helpers
# ---------------------------------------------------------------------------


def load_state(
    conversation_id: int,
    db: Session,
) -> Optional[models.ConversationState]:
    """Return the ConversationState row for this conversation, or ``None``."""
    return db.scalar(
        select(models.ConversationState).where(
            models.ConversationState.conversation_id == conversation_id
        )
    )


def _get_or_create_state(
    conversation_id: int,
    db: Session,
) -> models.ConversationState:
    """Return the existing state row or create a fresh one (not yet committed)."""
    state = load_state(conversation_id, db)
    if state is None:
        state = models.ConversationState(
            conversation_id=conversation_id,
            active_intent=None,
            active_order_id=None,
            active_tracking_number=None,
            pending_clarification=False,
        )
        db.add(state)
    return state


# ---------------------------------------------------------------------------
# Entity resolution - the core slot-filling logic
# ---------------------------------------------------------------------------


def resolve_entities(
    current_entities: dict[str, list[str]],
    intent: str,
    state: Optional[models.ConversationState],
) -> tuple[dict[str, list[str]], bool]:
    """Merge current-turn entities with stored slot memory.

    Parameters
    ----------
    current_entities:
        Raw entity dict from the NLP pipeline for the current message.
    intent:
        The classified intent for the current message.
    state:
        The persisted ``ConversationState`` row, or ``None`` for a new session.

    Returns
    -------
    resolved_entities:
        A copy of ``current_entities`` with missing slots filled from state
        where appropriate.
    ambiguous:
        ``True`` when the current message contains multiple *different*
        order IDs or multiple *different* tracking numbers, indicating the
        bot should ask the customer to clarify rather than picking one.
    """
    resolved = {k: list(v) for k, v in current_entities.items()}
    ambiguous = False

    order_ids: list[str] = resolved.get("order_ids", [])
    tracking_numbers: list[str] = resolved.get("tracking_numbers", [])

    # ------------------------------------------------------------------
    # Ambiguity check - multiple *distinct* identifiers in one message.
    # ------------------------------------------------------------------
    unique_orders = list(dict.fromkeys(oid.upper() for oid in order_ids))
    unique_tracking = list(dict.fromkeys(tn.upper() for tn in tracking_numbers))

    if len(unique_orders) > 1 or len(unique_tracking) > 1:
        ambiguous = True
        return resolved, ambiguous

    # ------------------------------------------------------------------
    # Topic-change guard - reset slots when the subject has moved on.
    # ------------------------------------------------------------------
    if intent in _TOPIC_CHANGE_INTENTS:
        # Don't pull old order context into a completely unrelated query.
        return resolved, ambiguous

    # ------------------------------------------------------------------
    # Slot carry-forward - fill missing identifiers from state.
    # ------------------------------------------------------------------
    if state is not None:
        # Order ID slot
        if not order_ids and state.active_order_id:
            resolved["order_ids"] = [state.active_order_id]

        # Tracking number slot
        if not tracking_numbers and state.active_tracking_number:
            resolved["tracking_numbers"] = [state.active_tracking_number]

    return resolved, ambiguous


# ---------------------------------------------------------------------------
# State update - called after each turn completes
# ---------------------------------------------------------------------------


def update_state(
    conversation_id: int,
    intent: str,
    resolved_entities: dict[str, list[str]],
    ambiguous: bool,
    db: Session,
) -> models.ConversationState:
    """Upsert the ConversationState row for this conversation.

    Parameters
    ----------
    conversation_id:
        The primary key of the Conversation row.
    intent:
        The intent classified for the current turn.
    resolved_entities:
        The fully-resolved entity dict (after carry-forward).
    ambiguous:
        Whether the current turn contained conflicting identifiers.
    db:
        An active SQLAlchemy session.

    Returns
    -------
    ConversationState
        The updated (but not yet committed) state row.
    """
    state = _get_or_create_state(conversation_id, db)

    # ------------------------------------------------------------------
    # Pending clarification flag
    # ------------------------------------------------------------------
    state.pending_clarification = ambiguous

    # ------------------------------------------------------------------
    # Topic-change -> wipe order/tracking slots
    # ------------------------------------------------------------------
    if intent in _TOPIC_CHANGE_INTENTS:
        state.active_intent = intent
        state.active_order_id = None
        state.active_tracking_number = None
        return state

    # ------------------------------------------------------------------
    # Update active intent (only overwrite with a meaningful one)
    # ------------------------------------------------------------------
    if intent != "unknown":
        state.active_intent = intent

    # ------------------------------------------------------------------
    # Do NOT update order/tracking slots when the turn was ambiguous.
    # We ask the customer to clarify instead of committing to an arbitrary ID.
    # ------------------------------------------------------------------
    if ambiguous:
        return state

    # ------------------------------------------------------------------
    # Update order ID slot
    # ------------------------------------------------------------------
    order_ids = resolved_entities.get("order_ids", [])
    if order_ids:
        new_order_id = order_ids[0].upper()
        state.active_order_id = new_order_id
    elif intent in _TOPIC_CHANGE_INTENTS:
        state.active_order_id = None

    # ------------------------------------------------------------------
    # Update tracking number slot
    # ------------------------------------------------------------------
    tracking_numbers = resolved_entities.get("tracking_numbers", [])
    if tracking_numbers:
        new_tracking = tracking_numbers[0].upper()
        state.active_tracking_number = new_tracking
    elif intent in _TOPIC_CHANGE_INTENTS:
        state.active_tracking_number = None

    return state


# ---------------------------------------------------------------------------
# Canned clarification response
# ---------------------------------------------------------------------------


def build_clarification_reply() -> str:
    """Return a polite clarification message for conflicting identifiers."""
    return (
        "I noticed multiple order or tracking identifiers in your message "
        "and I want to make sure I look up the right one. "
        "Could you please confirm which order ID or tracking number you'd "
        "like me to check?"
    )
