from pydantic import BaseModel, ConfigDict, Field

class MessageRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(
        min_length=1,
        max_length=2000,
        description="Customer message to validate",
    )


class MessageValidationResponse(BaseModel):
    valid: bool
    character_count: int
