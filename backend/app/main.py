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
)
from app.services.gemini import generate_reply


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
    conversation = models.Conversation(
        session_id=uuid4().hex,
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


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

    message = models.Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message



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
