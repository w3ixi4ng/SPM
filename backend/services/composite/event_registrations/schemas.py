from datetime import date, datetime, time
from typing import Literal
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
    # S-52: place in line, 1 = next; null unless waitlisted.
    position: int | None = None
    # S-55: a freed place is held for this Attendee until they answer.
    offered: bool = False


class WaitingListStatus(BaseModel):
    event_id: UUID
    waitlisted: bool
    joined_at: datetime
    # S-52
    position: int


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
    """S-48: one event the signed-in Attendee holds a place at.

    S-52: or is waiting for. A confirmed place has `registered_at`; a
    waiting-list entry has `joined_at` and its place in line instead.
    """

    event_id: UUID
    name: str | None
    start_date: date | None
    start_time: time | None
    end_date: date | None
    end_time: time | None
    # S-55: "offered" -- a waiting-list entry a freed place is held for.
    status: Literal["confirmed", "waitlisted", "offered"]
    registered_at: datetime | None
    joined_at: datetime | None
    position: int | None
    # S-56: false while a significant change is re-checked, with the dates
    # and times null. `venue` is the primary venue, for a held place only.
    details_confirmed: bool
    venue: str | None
