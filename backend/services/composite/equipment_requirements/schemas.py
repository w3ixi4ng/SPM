"""Browser-owned input for S-40 equipment requirements."""

from pydantic import BaseModel, ConfigDict, PositiveInt


class RequirementQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_quantity: PositiveInt
    impact_accepted: bool = False
