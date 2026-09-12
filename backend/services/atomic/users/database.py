"""Supabase clients for the users service.

Two clients, because they talk to two different things.

- ``supabase`` carries the service_role key and is the only one that touches
  ``users.users``. It bypasses row-level security, so it never leaves the
  backend.
- ``auth_client`` carries the anon key and is the one that talks to Supabase
  Auth. Signing up and signing in are anonymous operations; handing GoTrue the
  service_role key would authenticate the request itself as an administrator,
  which is not what a login is.

Neither client's stored session is ever read. A module-level client is shared
by every request, so ``sign_in_with_password`` leaving a session behind on it
is a race waiting to happen. Tokens are passed explicitly instead --
``get_user(jwt)``, ``refresh_session(refresh_token)`` -- and live in the
caller's cookies, not in this process.
"""

import os

from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
auth_client: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_db() -> Client:
    return supabase


def get_auth() -> Client:
    return auth_client
