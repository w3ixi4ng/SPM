from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel


class PublicEvent(BaseModel):
    """S-51: what anyone may read about a confirmed event without signing in."""

    id: UUID
    name: str | None
    purpose: str | None
    start_date: date | None
    start_time: time | None
    end_date: date | None
    end_time: time | None
    # The venues actually booked for it, by name.
    venues: list[str]
    registration_required: bool
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None


class RegistrationStatus(BaseModel):
    event_id: UUID
    registered: bool
    registered_at: datetime | None
