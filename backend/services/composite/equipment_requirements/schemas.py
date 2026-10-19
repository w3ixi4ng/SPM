"""Browser-owned input for S-40 equipment requirements and S-17 sign-off."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator


class RequirementQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_quantity: PositiveInt
    impact_accepted: bool = False


class SignoffDecision(str, Enum):
    APPROVED = "approved"
    DECLINED = "declined"


class SignoffRequest(BaseModel):
    """S-17: Technical Support approves, or declines with a reason. An
    approval over a shortage needs the comment the Coordinator will see.
    Repeated in backend/services/atomic/events/schemas.py
    (InternalTechnicalSignoff) -- change both."""

    model_config = ConfigDict(extra="forbid")

    decision: SignoffDecision
    reason: str | None = Field(default=None, max_length=500)
    override_comment: str | None = Field(default=None, max_length=500)

    @field_validator("reason", "override_comment", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def fields_match_decision(self):
        if self.decision is SignoffDecision.DECLINED:
            if self.reason is None:
                raise ValueError("reason is required to decline")
            if self.override_comment is not None:
                raise ValueError("override_comment is only given with an approval")
        elif self.reason is not None:
            raise ValueError("reason is not accepted when approving")
        return self
