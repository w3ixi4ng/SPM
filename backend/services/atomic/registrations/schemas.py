from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RegistrationCreate(BaseModel):
    """S-51: one Attendee taking a place at one event.

    The calling composite has already checked that the event is confirmed
    and its registration period is open; this service only records the place.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    attendee_id: UUID


class RegistrationRead(BaseModel):
    id: UUID
    event_id: UUID
    attendee_id: UUID
    created_at: datetime
