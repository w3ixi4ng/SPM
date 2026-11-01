"""Outbound HTTP clients for the event_requests composite service."""

import os

import httpx

USERS_URL = os.environ["USERS_SERVICE_URL"]
EVENTS_URL = os.environ["EVENTS_SERVICE_URL"]
NOTIFICATIONS_URL = os.environ["NOTIFICATIONS_SERVICE_URL"]
# S-61: an approved cancellation releases the event's venue bookings.
BOOKINGS_URL = os.environ["BOOKINGS_SERVICE_URL"]
EQUIPMENT_URL = os.environ["EQUIPMENT_SERVICE_URL"]
# S-69: an approved cancellation notifies the event's Attendees.
REGISTRATIONS_URL = os.environ["REGISTRATIONS_SERVICE_URL"]
# S-89: S-77's affected-booking flag comes from the composite that owns it.
VENUE_BOOKINGS_URL = os.environ["VENUE_BOOKINGS_SERVICE_URL"]
VENUES_URL = os.environ["VENUES_SERVICE_URL"]


def assignment_service_headers() -> dict[str, str]:
    """Server-owned credential, never copied from an incoming browser request."""
    secret = os.environ.get("ASSIGNMENT_SERVICE_SECRET")
    if not secret:
        raise RuntimeError("Assignment service is not configured")
    return {"X-Assignment-Service-Token": secret}


def get_users_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=USERS_URL, timeout=5.0)


def get_events_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EVENTS_URL, timeout=5.0)


def get_notifications_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=NOTIFICATIONS_URL, timeout=5.0)


def get_bookings_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BOOKINGS_URL, timeout=5.0)


def get_equipment_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EQUIPMENT_URL, timeout=5.0)


def get_registrations_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=REGISTRATIONS_URL, timeout=5.0)


def get_venue_bookings_client() -> httpx.AsyncClient:
    # The flag read checks a venue and its periods per booking, so it gets
    # longer than a single atomic read.
    return httpx.AsyncClient(base_url=VENUE_BOOKINGS_URL, timeout=15.0)


def get_venues_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=VENUES_URL, timeout=5.0)
