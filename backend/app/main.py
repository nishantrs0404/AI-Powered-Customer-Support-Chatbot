
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import Base, engine, get_db
from app.schemas.conversation import ConversationResponse
from app.schemas.message import (
    MessageRequest,
    MessageResponse,
    MessageValidationResponse,
)


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


@app.get("/health", tags=["Health"])
def health_check():
    """Check whether the backend service is running."""
    return {
        "status": "ok",
        "service": "customer-support-chatbot",
    }


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
