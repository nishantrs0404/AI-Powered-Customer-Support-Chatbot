"""Pydantic schemas for NLP intent classification and entity extraction."""

from typing import Any
from pydantic import BaseModel, Field


class NLPRequest(BaseModel):
    """Request payload for NLP processing."""

    message: str = Field(min_length=1, max_length=2000, description="Customer message to analyze")


class EntityResponse(BaseModel):
    """Extracted domain entities."""

    order_ids: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    tracking_numbers: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)


class IntentResponse(BaseModel):
    """Intent classification response."""

    intent: str
    confidence: float
    matched_keywords: list[str] = Field(default_factory=list)
    matched_patterns: list[str] = Field(default_factory=list)


class MessageAnalysisResponse(BaseModel):
    """Full message NLP analysis response."""

    text: str
    normalized: str
    tokens: list[str]
    intent: str
    confidence: float
    entities: EntityResponse
    is_confident: bool
