"""Browser input for S-86 Operational Safety Check decisions."""

from enum import Enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class SafetyDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class SafetyDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: SafetyDecision
    reason: str | None = None
    expected_event_updated_at: datetime

    @field_validator("reason", mode="before")
    @classmethod
    def normalise_reason(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def reason_matches_decision(self):
        if self.decision in (SafetyDecision.REJECTED, SafetyDecision.CHANGES_REQUESTED):
            if self.reason is None:
                raise ValueError("reason is required to reject or request changes")
        elif self.reason is not None:
            raise ValueError("reason is not accepted when approving a safety check")
        return self

