"""The Supabase client the integration and e2e suites use for setup, checks
and cleanup.

The same as `supabase.create_client`, except that a connection which fails
before the request is sent -- a TLS handshake reset, a refused connect -- is
retried. CI talks to a hosted project over the internet, and one dropped
handshake in a fixture's teardown was failing an otherwise green run.
Retrying is safe even for writes: nothing reached the database.
"""

import httpx
from supabase import Client, ClientOptions
from supabase import create_client as _create_client

CONNECT_RETRIES = 3
# supabase-py's own default request timeout, which a custom client replaces.
TIMEOUT = httpx.Timeout(120.0)


def create_client(url: str, key: str) -> Client:
    http = httpx.Client(transport=httpx.HTTPTransport(retries=CONNECT_RETRIES), timeout=TIMEOUT)
    return _create_client(url, key, options=ClientOptions(httpx_client=http))
