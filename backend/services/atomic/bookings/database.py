"""Supabase client for the bookings service."""

import os

from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# Only this service_role client may access bookings.bookings.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
auth_client: Client = create_client(SUPABASE_URL, os.environ["SUPABASE_ANON_KEY"])


def get_db() -> Client:
    return supabase


def get_auth() -> Client:
    return auth_client
