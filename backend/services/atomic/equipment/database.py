"""Supabase clients for the equipment service."""

import os

from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

# Only the backend service-role client accesses equipment.equipment.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Authentication uses the public Auth client with the caller's cookie token.
auth_client: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_db() -> Client:
    return supabase


def get_auth() -> Client:
    return auth_client
