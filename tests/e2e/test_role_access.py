"""TC-E2E-204 -- role access, end to end.

`frontend/src/lib/access.js` mirrors the policy in the events service's
authorization.py. Nothing checks that the two agree; this does, through a real
login and a real redirect.
"""

import re

from .conftest import requires_env

pytestmark = requires_env


# --- TC-E2E-204 -----------------------------------------------------------
def test_venue_staff_cannot_reach_the_organiser_dashboard(page, make_user, sign_in):
    user = make_user("venue_staff")

    sign_in(user)
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)

    # Typed straight into the address bar, not followed from a link.
    page.goto("/dashboard/event-organiser")
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)

    # And the organiser-only route is refused the same way.
    page.goto("/events/new")
    page.wait_for_url(re.compile(r"/dashboard/venue-staff$"), timeout=20000)
