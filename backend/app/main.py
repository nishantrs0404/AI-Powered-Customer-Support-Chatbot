import asyncio
import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import Base, engine, get_db
from app.faq_data import FAQS
from app.schemas.conversation import ConversationResponse
from app.schemas.faq import (
    FAQResult,
    FAQSearchRequest,
    FAQSearchResponse,
)
from app.schemas.message import (
    MessageRequest,
    MessageResponse,
    MessageValidationResponse,
    ReplyResponse,
)
from app.nlp import analyze_message, classify_intent, extract_entities
from app.schemas.nlp import (
    EntityResponse,
    IntentResponse,
    MessageAnalysisResponse,
    NLPRequest,
)
from app.services.context_builder import build_context, format_context_for_prompt
from app.services.conversation_state import (
    build_clarification_reply,
    load_state,
    resolve_entities,
    update_state,
)
from app.services.faq_search import search_faqs as faq_service_search
from app.services.gemini import generate_context_aware_reply, generate_reply
from app.services.prompts import FAQ_RELEVANCE_THRESHOLD, HISTORY_LIMIT, SYSTEM_PROMPT


# Gemini request and response schemas

class AIReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AIReplyResponse(BaseModel):
    reply: str


# Application startup

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables when the application starts."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AI-Powered Customer Support Chatbot",
    description="Backend API for the customer support chatbot.",
    version="0.1.0",
    lifespan=lifespan,
)



# Health endpoint

@app.get("/health", tags=["Health"])
def health_check():
    """Check whether the backend service is running."""
    return {
        "status": "ok",
        "service": "customer-support-chatbot",
    }


# Message validation

@app.post(
    "/api/v1/validate-message",
    response_model=MessageValidationResponse,
    tags=["Messages"],
)
def validate_message(
    request: MessageRequest,
) -> MessageValidationResponse:
    """Validate a customer message and return its character count."""
    return MessageValidationResponse(
        valid=True,
        character_count=len(request.message),
    )


# Conversation management

@app.post(
    "/api/v1/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Conversations"],
)
def create_conversation(
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """Create and persist a new conversation."""
    try:
        conversation = models.Conversation(
            session_id=uuid4().hex,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return conversation
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while creating conversation.",
        ) from exc


# Save a customer message


@app.post(
    "/api/v1/conversations/{session_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Messages"],
)
def create_message(
    session_id: str,
    request: MessageRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Save a customer message to an existing conversation."""
    conversation = db.scalar(
        select(models.Conversation).where(
            models.Conversation.session_id == session_id
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    try:
        message = models.Message(
            conversation_id=conversation.id,
            role="user",
            content=request.message,
        )

        db.add(message)
        db.commit()
        db.refresh(message)

        return message
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while saving message.",
        ) from exc



# Retrieve conversation history


@app.get(
    "/api/v1/conversations/{session_id}/messages",
    response_model=list[MessageResponse],
    tags=["Messages"],
)
def get_conversation_messages(
    session_id: str,
    db: Session = Depends(get_db),
) -> list[MessageResponse]:
    """Retrieve conversation messages in insertion order."""
    conversation = db.scalar(
        select(models.Conversation).where(
            models.Conversation.session_id == session_id
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = db.scalars(
        select(models.Message)
        .where(
            models.Message.conversation_id == conversation.id
        )
        .order_by(models.Message.id.asc())
    ).all()

    return list(messages)



# Gemini AI reply


@app.post(
    "/ai/reply",
    response_model=AIReplyResponse,
    tags=["AI"],
)
async def create_ai_reply(
    request: AIReplyRequest,
) -> AIReplyResponse:
    """Generate a customer-support response using Gemini."""
    try:
        reply = await asyncio.to_thread(
            generate_reply,
            request.message,
        )

        return AIReplyResponse(reply=reply)

    except RuntimeError as exc:
        error_message = str(exc)

        if "not configured" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gemini API key is not configured.",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gemini could not generate a response. Please try again.",
        ) from exc


# Context-aware AI reply with conversation history


@app.post(
    "/api/v1/conversations/{session_id}/reply",
    response_model=ReplyResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["AI"],
)
async def create_context_aware_reply(
    session_id: str,
    request: MessageRequest,
    db: Session = Depends(get_db),
) -> ReplyResponse:
    """
    Save a customer message, search the FAQ database for a relevant answer,
    and fall back to a context-aware Gemini reply when no sufficient FAQ match
    is found.  Persists both the customer message and the assistant response.

    The response includes an ``answer_source`` field that is either ``"faq"``
    (answer served directly from the FAQ dataset) or ``"gemini"`` (answer
    generated by the Gemini API).
    """
    # Verify the conversation exists and belongs to this session.
    conversation = db.scalar(
        select(models.Conversation).where(
            models.Conversation.session_id == session_id
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Persist the incoming user message first to guarantee it is stored
    # even if the downstream FAQ / Gemini call fails.
    try:
        user_message = models.Message(
            conversation_id=conversation.id,
            role="user",
            content=request.message,
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while processing message.",
        ) from exc

    # ------------------------------------------------------------------
    # NLP Intent Classification & Entity Extraction
    # (Run BEFORE FAQ/Gemini so context can be built for the Gemini path.)
    # ------------------------------------------------------------------
    intent_result = classify_intent(request.message)
    extracted_entities = extract_entities(request.message)

    # ------------------------------------------------------------------
    # Day 21: Multi-turn conversational state tracking
    # Load prior state and resolve entities using slot memory.
    # ------------------------------------------------------------------
    prior_state = load_state(conversation.id, db)
    resolved_entity_dict, is_ambiguous = resolve_entities(
        extracted_entities.to_dict(),
        intent_result.intent,
        prior_state,
    )

    # When the customer provided conflicting identifiers, ask for
    # clarification immediately — skip FAQ/Gemini for this turn.
    if is_ambiguous:
        clarification_text = build_clarification_reply()
        answer_source = "gemini"  # Treat as a generated response.

        try:
            # Update state to record the ambiguous turn.
            update_state(
                conversation.id,
                intent_result.intent,
                resolved_entity_dict,
                is_ambiguous,
                db,
            )
            assistant_message = models.Message(
                conversation_id=conversation.id,
                role="assistant",
                content=clarification_text,
            )
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error while saving clarification response.",
            ) from exc

        return ReplyResponse(
            id=assistant_message.id,
            conversation_id=assistant_message.conversation_id,
            role=assistant_message.role,
            content=assistant_message.content,
            created_at=assistant_message.created_at,
            answer_source=answer_source,
            intent=intent_result.intent,
            entities=resolved_entity_dict,
        )

    # ------------------------------------------------------------------
    # FAQ-first routing
    # Search the FAQ dataset for a sufficiently relevant answer.
    # search_faqs() returns results sorted by descending score and already
    # filtered by min_score (defaults to FAQ_RELEVANCE_THRESHOLD).
    # ------------------------------------------------------------------
    try:
        faq_hits = faq_service_search(
            request.message,
            limit=1,
            min_score=FAQ_RELEVANCE_THRESHOLD,
        )
    except Exception:
        # If FAQ search encounters an unexpected issue, safely fall back to Gemini
        faq_hits = []

    if faq_hits:
        # A reliable FAQ answer exists — return it without calling Gemini.
        faq_answer = faq_hits[0]["answer"]
        answer_source: str = "faq"
    else:
        # ------------------------------------------------------------------
        # Business context retrieval (Day 19-20)
        # Build grounded context from intent + *resolved* entities (Day 21).
        # ------------------------------------------------------------------
        try:
            business_context = build_context(
                request.message,
                intent_result.intent,
                resolved_entity_dict,
            )
            context_text = format_context_for_prompt(business_context)
        except Exception:
            # If context retrieval fails, continue without it.
            context_text = ""

        # Build the augmented system prompt with business context.
        if context_text:
            augmented_prompt = SYSTEM_PROMPT + "\n\n" + context_text
        else:
            augmented_prompt = SYSTEM_PROMPT

        # ------------------------------------------------------------------
        # Gemini fallback
        # Retrieve the N most recent messages *excluding* the one just saved
        # so it is not duplicated when we pass history to Gemini.
        # ------------------------------------------------------------------
        recent_rows = db.scalars(
            select(models.Message)
            .where(
                models.Message.conversation_id == conversation.id,
                models.Message.id != user_message.id,
            )
            .order_by(models.Message.id.desc())
            .limit(HISTORY_LIMIT)
        ).all()

        # Restore chronological order (oldest first).
        history = [
            {"role": row.role, "content": row.content}
            for row in reversed(recent_rows)
        ]

        # Call Gemini with the augmented system prompt, history, and current message.
        try:
            faq_answer = await asyncio.to_thread(
                generate_context_aware_reply,
                request.message,
                history,
                augmented_prompt,
            )
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            error_message = str(exc)

            if "not configured" in error_message.lower() or "missing" in error_message.lower():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Gemini API key is not configured.",
                ) from exc

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini could not generate a response. Please try again.",
            ) from exc

        answer_source = "gemini"

    # ------------------------------------------------------------------
    # Day 21: Persist updated conversational state after each successful turn.
    # ------------------------------------------------------------------
    try:
        update_state(
            conversation.id,
            intent_result.intent,
            resolved_entity_dict,
            is_ambiguous,
            db,
        )
    except Exception:
        # State tracking must never break the primary reply flow.
        pass

    # Persist the assistant response.
    try:
        assistant_message = models.Message(
            conversation_id=conversation.id,
            role="assistant",
            content=faq_answer,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while saving response.",
        ) from exc

    # Build and return the extended reply response.
    return ReplyResponse(
        id=assistant_message.id,
        conversation_id=assistant_message.conversation_id,
        role=assistant_message.role,
        content=assistant_message.content,
        created_at=assistant_message.created_at,
        answer_source=answer_source,
        intent=intent_result.intent,
        entities=resolved_entity_dict,
    )


# FAQ search


@app.post(
    "/api/v1/faqs/search",
    response_model=FAQSearchResponse,
    tags=["FAQs"],
)
def search_faqs(
    request: FAQSearchRequest,
) -> FAQSearchResponse:
    """Search sample FAQs using keyword overlap."""

    stop_words = {
        "a", "an", "the", "is", "are", "am",
        "i", "my", "me", "to", "for", "of",
        "and", "in", "on", "do", "does", "how",
        "can", "what", "where", "please",
    }

    def tokenize(text: str) -> set[str]:
        words = set(
            re.findall(r"\b[a-z0-9]+\b", text.lower())
        )
        return words - stop_words

    query_words = tokenize(request.query)

    if not query_words:
        return FAQSearchResponse(
            query=request.query,
            results=[],
        )

    matches = []

    for faq in FAQS:
        question_words = tokenize(faq["question"])
        answer_words = tokenize(faq["answer"])

        searchable_words = question_words | answer_words
        overlap = query_words & searchable_words

        if not overlap:
            continue

        score = len(overlap) / len(query_words)

        matches.append(
            FAQResult(
                id=faq["id"],
                question=faq["question"],
                answer=faq["answer"],
                score=round(score, 4),
            )
        )

    matches.sort(
        key=lambda item: item.score,
        reverse=True,
    )

    return FAQSearchResponse(
        query=request.query,
        results=matches[:request.limit],
    )


# ----------------------------------------------------------------------
# NLP Endpoints (FR-04 Intent Recognition & FR-05 Entity Extraction)
# ----------------------------------------------------------------------


@app.post(
    "/api/v1/nlp/intent",
    response_model=IntentResponse,
    tags=["NLP"],
)
def get_intent(request: NLPRequest) -> IntentResponse:
    """Classify the customer message intent across 13 supported categories."""
    result = classify_intent(request.message)
    return IntentResponse(
        intent=result.intent,
        confidence=result.confidence,
        matched_keywords=result.matched_keywords,
        matched_patterns=result.matched_patterns,
    )


@app.post(
    "/api/v1/nlp/entities",
    response_model=EntityResponse,
    tags=["NLP"],
)
def get_entities(request: NLPRequest) -> EntityResponse:
    """Extract domain entities (Order IDs, tracking numbers, emails, etc.)."""
    entities = extract_entities(request.message)
    return EntityResponse(
        order_ids=entities.order_ids,
        emails=entities.emails,
        tracking_numbers=entities.tracking_numbers,
        amounts=entities.amounts,
        products=entities.products,
    )


@app.post(
    "/api/v1/nlp/analyze",
    response_model=MessageAnalysisResponse,
    tags=["NLP"],
)
def analyze(request: NLPRequest) -> MessageAnalysisResponse:
    """Perform complete NLP analysis: preprocessing, intent detection, and entity extraction."""
    analysis = analyze_message(request.message)
    return MessageAnalysisResponse(
        text=analysis["text"],
        normalized=analysis["normalized"],
        tokens=analysis["tokens"],
        intent=analysis["intent"],
        confidence=analysis["confidence"],
        entities=EntityResponse(**analysis["entities"]),
        is_confident=analysis["is_confident"],
    )
