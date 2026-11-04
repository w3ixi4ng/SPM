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
    expected attendance, so the freed place is offered to the next Attendee
    waiting (S-55) only while one is genuinely free; 0 offers it to no one."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    attendee_id: UUID
    capacity: int = Field(ge=0)


class OfferAcceptanceCreate(BaseModel):
    """S-55: the invited Attendee taking the place held for them."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    attendee_id: UUID


class OfferDeclineCreate(BaseModel):
    """S-55: the invited Attendee passing on the place. `capacity` as for a
    withdrawal: the place is offered to the next in line only while free."""

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
    # S-55: when this entry was offered a freed place; null while waiting.
    offered_at: datetime | None = None


class WithdrawalRead(BaseModel):
    withdrawn: RegistrationRead
    # S-55: the entry the freed place is now held for, if anyone's.
    offered: WaitingListRead | None


class OfferDeclineRead(BaseModel):
    declined: WaitingListRead
    offered: WaitingListRead | None


class WithdrawalRecordRead(BaseModel):
    """S-58: an event this Attendee gave up a place (or an offered one) at,
    and when they last did."""

    id: UUID
    event_id: UUID
    attendee_id: UUID
    withdrawn_at: datetime
