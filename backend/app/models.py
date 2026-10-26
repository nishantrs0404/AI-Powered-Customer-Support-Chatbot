from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    state: Mapped["ConversationState"] = relationship(
        back_populates="conversation",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages"
    )


class ConversationState(Base):
    """Persistent slot-filling state for a single conversation session.

    One row per conversation.  Tracks the active business entities so that
    follow-up messages can resolve pronoun and implicit references without
    the customer repeating themselves.

    Design rules
    ------------
    - ``active_order_id`` and ``active_tracking_number`` are cleared when the
      customer explicitly provides a *different* identifier or changes to an
      unrelated topic (greeting, account, technical_issue, payment, complaint).
    - ``pending_clarification`` is set when multiple conflicting identifiers
      are present and cleared as soon as the customer disambiguates.
    - Only the most recently confirmed identifier for each slot is stored; we
      never accumulate a list here — the full message history handles that.
    """

    __tablename__ = "conversation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), unique=True, nullable=False, index=True
    )

    # The last confidently-classified intent (excluding "unknown").
    active_intent: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # The single order ID currently in focus for this session.
    active_order_id: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # The single tracking number currently in focus.
    active_tracking_number: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # True when the last user turn introduced ambiguous / conflicting
    # identifiers and the bot asked for clarification.
    pending_clarification: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="state")

