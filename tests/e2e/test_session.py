"""TC-E2E-202 -- the session's whole life, through the gateway.

Proves the httpOnly cookies are set on login and really gone after sign-out:
a route guard that only checked client state would pass the first half of this
and fail the last line.
"""

import re

from .conftest import requires_env

pytestmark = requires_env


# --- TC-E2E-202 -----------------------------------------------------------
def test_log_in_then_sign_out_closes_the_session(page, make_user, sign_in):
    user = make_user("event_organiser")

    sign_in(user)
    page.wait_for_url(re.compile(r"/dashboard/event-organiser$"), timeout=20000)

    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url(re.compile(r"/login$"), timeout=20000)

    # The cookies are the session, so this is the real check: a deep link to a
    # protected route has to bounce now, not render from stale client state.
    page.goto("/dashboard/event-organiser")
    page.wait_for_url(re.compile(r"/login$"), timeout=20000)
