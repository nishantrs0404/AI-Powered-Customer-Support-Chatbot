
from fastapi import FastAPI

from app.schemas.message import (
    MessageRequest,
    MessageValidationResponse,
)

app = FastAPI(
    title="AI-Powered Customer Support Chatbot",
    description="Backend API for the customer support chatbot.",
    version="0.1.0",
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
