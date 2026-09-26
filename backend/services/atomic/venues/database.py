"""Supabase clients for the venues service."""

import os

from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

# Only this service_role client may access venues.venues.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Authentication uses the anon client. Session tokens are always supplied
# explicitly from the caller's cookies; no shared client session is trusted.
auth_client: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_db() -> Client:
    return supabase


def get_auth() -> Client:
    return auth_client
