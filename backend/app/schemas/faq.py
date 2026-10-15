
from pydantic import BaseModel, Field


class FAQSearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=500,
        description="Customer question to search for",
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of FAQ results",
    )


class FAQResult(BaseModel):
    id: str
    question: str
    answer: str
    score: float


class FAQSearchResponse(BaseModel):
    query: str
    results: list[FAQResult]
