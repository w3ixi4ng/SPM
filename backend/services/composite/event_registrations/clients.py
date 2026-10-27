"""Bounded outbound clients for the S-51 event_registrations composite."""

import os
from datetime import datetime, timezone

import httpx

TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


def _client(variable: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=os.environ[variable], timeout=TIMEOUT)


def get_users_client() -> httpx.AsyncClient:
    return _client("USERS_SERVICE_URL")


def get_events_client() -> httpx.AsyncClient:
    return _client("EVENTS_SERVICE_URL")


def get_bookings_client() -> httpx.AsyncClient:
    return _client("BOOKINGS_SERVICE_URL")


def get_venues_client() -> httpx.AsyncClient:
    return _client("VENUES_SERVICE_URL")


def get_registrations_client() -> httpx.AsyncClient:
    return _client("REGISTRATIONS_SERVICE_URL")


def get_notifications_client() -> httpx.AsyncClient:
    return _client("NOTIFICATIONS_SERVICE_URL")


def get_now() -> datetime:
    """The current instant, as a dependency so tests can fix the clock."""
    return datetime.now(timezone.utc)
