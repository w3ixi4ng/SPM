"""Outbound HTTP clients for the venue_bookings composite service."""

import os

import httpx

USERS_URL = os.environ["USERS_SERVICE_URL"]
EVENTS_URL = os.environ["EVENTS_SERVICE_URL"]
VENUES_URL = os.environ["VENUES_SERVICE_URL"]
BOOKINGS_URL = os.environ["BOOKINGS_SERVICE_URL"]


def get_users_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=USERS_URL, timeout=5.0)


def get_events_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EVENTS_URL, timeout=5.0)


def get_venues_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=VENUES_URL, timeout=5.0)


def get_bookings_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BOOKINGS_URL, timeout=5.0)
