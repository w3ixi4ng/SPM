"""Outbound HTTP clients for the venue_bookings composite service."""

import os

import httpx

USERS_URL = os.environ["USERS_SERVICE_URL"]
EVENTS_URL = os.environ["EVENTS_SERVICE_URL"]
VENUES_URL = os.environ["VENUES_SERVICE_URL"]
BOOKINGS_URL = os.environ["BOOKINGS_SERVICE_URL"]
BOOKINGS_TIMEOUT = 15.0
INTERNAL_READ_TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=10.0,
    write=5.0,
    pool=5.0,
)


def get_users_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=USERS_URL, timeout=INTERNAL_READ_TIMEOUT)


def get_events_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EVENTS_URL, timeout=INTERNAL_READ_TIMEOUT)


def get_venues_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=VENUES_URL, timeout=INTERNAL_READ_TIMEOUT)


def get_bookings_client() -> httpx.AsyncClient:
    # Booking writes can include Supabase constraint checks. Allow for CI and
    # remote-database latency while retaining a bounded downstream call.
    return httpx.AsyncClient(base_url=BOOKINGS_URL, timeout=BOOKINGS_TIMEOUT)
