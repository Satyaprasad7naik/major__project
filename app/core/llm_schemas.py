from pydantic import BaseModel, Field
from typing import Literal, Optional


class IntentClassification(BaseModel):
    intent: Literal["SELECT", "UPDATE", "DELETE", "INSERT", "SCHEMA_QUERY", "OFF_TOPIC", "UNKNOWN"]
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    complexity: Literal["Simple", "Medium", "Complex"] = "Simple"
    needs_clarification: bool = False
    off_topic_reason: Optional[str] = None
    clarity_score: float = Field(ge=0.0, le=1.0, default=0.5)


SAFE_FALLBACK_INTENT = IntentClassification(
    intent="UNKNOWN",
    confidence=0.0,
    needs_clarification=True,
)