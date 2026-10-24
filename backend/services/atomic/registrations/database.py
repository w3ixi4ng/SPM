"""Supabase client for the registrations service."""

import os

from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# Only this service_role client may access registrations.registrations.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_db() -> Client:
    return supabase
