"""Bounded outbound clients for the S-86 safety_checks composite."""

import os

import httpx

TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


def _client(variable: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=os.environ[variable], timeout=TIMEOUT)


def get_users_client() -> httpx.AsyncClient:
    return _client("USERS_SERVICE_URL")


def get_events_client() -> httpx.AsyncClient:
    return _client("EVENTS_SERVICE_URL")


def get_venues_client() -> httpx.AsyncClient:
    return _client("VENUES_SERVICE_URL")


def get_bookings_client() -> httpx.AsyncClient:
    return _client("BOOKINGS_SERVICE_URL")


def get_equipment_client() -> httpx.AsyncClient:
    return _client("EQUIPMENT_SERVICE_URL")


def get_notifications_client() -> httpx.AsyncClient:
    return _client("NOTIFICATIONS_SERVICE_URL")

