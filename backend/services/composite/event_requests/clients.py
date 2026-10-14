"""Outbound HTTP clients for the event_requests composite service."""

import os

import httpx

USERS_URL = os.environ["USERS_SERVICE_URL"]
EVENTS_URL = os.environ["EVENTS_SERVICE_URL"]
NOTIFICATIONS_URL = os.environ["NOTIFICATIONS_SERVICE_URL"]
# S-61: an approved cancellation releases the event's venue bookings.
BOOKINGS_URL = os.environ["BOOKINGS_SERVICE_URL"]


def get_users_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=USERS_URL, timeout=5.0)


def get_events_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EVENTS_URL, timeout=5.0)


def get_notifications_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=NOTIFICATIONS_URL, timeout=5.0)


def get_bookings_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BOOKINGS_URL, timeout=5.0)
