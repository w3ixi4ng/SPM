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
    # S-50: whether a place is left, and whether the Organiser closed
    # registration early. The cap itself (expected attendance) stays private.
    registration_closed_by_organiser: bool
    is_full: bool


class RegistrationStatus(BaseModel):
    event_id: UUID
    registered: bool
    registered_at: datetime | None
    # S-50: on the waiting list of a full event.
    waitlisted: bool = False
    joined_at: datetime | None = None


class WaitingListStatus(BaseModel):
    event_id: UUID
    waitlisted: bool
    joined_at: datetime


class EventAttendee(BaseModel):
    """S-48: one place at the event, as its Organiser sees it."""

    attendee_id: UUID
    name: str | None
    email: str | None
    registered_at: datetime


class WaitingAttendee(BaseModel):
    """S-50: one Attendee waiting for a place, as the Organiser sees them."""

    attendee_id: UUID
    name: str | None
    email: str | None
    joined_at: datetime


class EventAttendees(BaseModel):
    event_id: UUID
    count: int
    attendees: list[EventAttendee]
    # S-50: oldest first.
    waiting_list: list[WaitingAttendee] = []


class MyRegistration(BaseModel):
    """S-48: one event the signed-in Attendee holds a place at."""

    event_id: UUID
    name: str | None
    start_date: date | None
    start_time: time | None
    end_date: date | None
    end_time: time | None
    registered_at: datetime
