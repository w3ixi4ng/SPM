"""S-91 AC2 (attendee half) and S-56 AC3: every attendee-facing view names
only the venue the Coordinator marked primary -- TC-EVENTREGISTRATIONS-051.

The public list, the public event page, the Attendee's own list and the
registration confirmation each read the venue separately, so each is checked.
"""

from .conftest import ATTENDEE_A, EVENT_E, response

MINE = "/event-registrations/me/registrations"
REGISTER_E = f"/event-registrations/events/{EVENT_E}/registration"

# B1 confirmed but secondary; B2 the primary; B3 marked primary but only held,
# so the marker must not count.
BOOKINGS = [
    {"id": "b1", "venue_id": "v-b1", "venue_name": "Room B", "status": "confirmed",
     "is_primary": False, "submitted_at": "2026-09-01T02:00:00Z"},
    {"id": "b2", "venue_id": "v-b2", "venue_name": "Hall A", "status": "confirmed",
     "is_primary": True, "submitted_at": "2026-10-01T02:00:00Z"},
    {"id": "b3", "venue_id": "v-b3", "venue_name": "Hall C", "status": "held",
     "is_primary": True, "submitted_at": "2026-08-01T02:00:00Z"},
]
NAMES = {"v-b1": "Room B", "v-b2": "Hall A", "v-b3": "Hall C"}
SECONDARY = ("Room B", "Hall C")


def _three_bookings(services):
    async def bookings_get(path, params=None, **kwargs):
        return response(200, BOOKINGS if params and params.get("event_id") == EVENT_E else [])

    async def venues_get(path, **kwargs):
        venue_id = path.rsplit("/", 1)[-1]
        return response(200, {"id": venue_id, "name": NAMES[venue_id]})

    services["bookings"].get.side_effect = bookings_get
    services["venues"].get.side_effect = venues_get


# --- TC-EVENTREGISTRATIONS-051 --------------------------------------------
def test_attendees_receive_only_the_explicitly_primary_venue(client, services):
    _three_bookings(services)

    # 1. Public list, signed out.
    listed = client.get("/event-registrations/events")
    assert listed.status_code == 200
    e = next(row for row in listed.json() if row["id"] == EVENT_E)
    assert e["venues"] == ["Hall A"]

    # 2. Public event page.
    detail = client.get(f"/event-registrations/events/{EVENT_E}")
    assert detail.status_code == 200
    assert detail.json()["venues"] == ["Hall A"]

    # 3. The Attendee's own list, holding a place.
    place = {"id": "r-a", "event_id": EVENT_E, "attendee_id": ATTENDEE_A, "created_at": "2026-11-05T04:00:00Z"}
    services["registrations"].places[EVENT_E] = [place]
    base = services["registrations"].get.side_effect

    async def registrations_get(path, **kwargs):
        if path == f"/registrations/attendees/{ATTENDEE_A}":
            return response(200, services["registrations"].places[EVENT_E])
        return await base(path, **kwargs)

    services["registrations"].get.side_effect = registrations_get
    mine = client.get(MINE)
    assert mine.status_code == 200
    row = next(item for item in mine.json() if item["event_id"] == EVENT_E)
    assert row["venue"] == "Hall A"

    # 4. The registration confirmation's wording.
    services["registrations"].places[EVENT_E] = []
    services["notifications"].post.reset_mock()
    registered = client.post(REGISTER_E)
    assert registered.status_code == 201, registered.text
    messages = [
        n["message"]
        for call in services["notifications"].post.call_args_list
        for n in call.kwargs["json"]["notifications"]
    ]
    assert len(messages) == 1 and "at Hall A." in messages[0]

    everything = str([listed.json(), detail.json(), mine.json(), messages])
    for name in SECONDARY:
        assert name not in everything
