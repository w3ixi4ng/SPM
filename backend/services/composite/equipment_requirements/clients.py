"""Outbound clients for the equipment_requirements composite."""

import os

import httpx

USERS_URL = os.environ["USERS_SERVICE_URL"]
EVENTS_URL = os.environ["EVENTS_SERVICE_URL"]
EQUIPMENT_URL = os.environ["EQUIPMENT_SERVICE_URL"]


def get_users_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=USERS_URL, timeout=5.0)


def get_events_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EVENTS_URL, timeout=5.0)


def get_equipment_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EQUIPMENT_URL, timeout=5.0)
