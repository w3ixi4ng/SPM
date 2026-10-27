from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegistrationCreate(BaseModel):
    """S-51: one Attendee taking a place at one event.

    The calling composite has already checked that the event is confirmed
    and its registration period is open; this service only records the place.

    S-50: and only while one is left. `capacity` is the event's expected
    attendance, which the events service owns, so the caller supplies it.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    attendee_id: UUID
    capacity: int = Field(gt=0)


class WaitingListCreate(BaseModel):
    """S-50: an Attendee waiting for a place at a full event."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    attendee_id: UUID


class WithdrawalCreate(BaseModel):
    """S-53: an Attendee giving up their place. `capacity` is the event's
    expected attendance, so the freed place goes to the next Attendee waiting
    only while one is genuinely free; 0 promotes no one."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    attendee_id: UUID
    capacity: int = Field(ge=0)


class RegistrationRead(BaseModel):
    id: UUID
    event_id: UUID
    attendee_id: UUID
    created_at: datetime


class WaitingListRead(BaseModel):
    id: UUID
    event_id: UUID
    attendee_id: UUID
    created_at: datetime


class WithdrawalRead(BaseModel):
    withdrawn: RegistrationRead
    promoted: RegistrationRead | None
