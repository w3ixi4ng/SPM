"""Supabase client for the bookings service."""

import os

from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# Only this service_role client may access bookings.bookings. There is no
# anon/auth client: this service has no browser routes and authenticates no
# one -- its only caller is the venue_bookings composite, which already has.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_db() -> Client:
    return supabase
