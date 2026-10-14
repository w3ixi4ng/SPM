"""TC-BOOKINGS-109 (S-75): the setup/turnaround gap against real rows."""
import uuid

import httpx

from .conftest import BASE_URL, requires_env
from .test_decision import actors, create_booking  # noqa: F401 -- actors is a fixture

pytestmark = requires_env

GAP = {"setup_minutes": 30, "turnaround_minutes": 45}


def test_the_setup_turnaround_gap_is_enforced_against_real_rows(booking_ids, actors):
    _, staff = actors("venue_staff")
    venue_id = str(uuid.uuid4())
    a = create_booking(booking_ids, venue_id=venue_id, start_time="10:00", end_time="12:00")
    approved = httpx.post(f"{BASE_URL}/bookings/{a['id']}/decision", headers=staff,
                          json={"decision": "approved"}, timeout=15)
    assert approved.status_code == 200, approved.text

    def request(start, end):
        return httpx.post(f"{BASE_URL}/bookings", params=GAP, timeout=15, json={
            "event_id": str(uuid.uuid4()), "venue_id": venue_id, "coordinator_id": str(uuid.uuid4()),
            "coordinator_name": "Test Coordinator", "coordinator_email": "coordinator@example.com",
            "booking_date": "2026-11-12", "start_time": start, "end_time": end,
            "event_name": "spm-test S75", "event_purpose": "Gap testing", "expected_attendance": 10,
            "venue_name": "Studio B",
        })

    inside = request("12:30", "13:00")
    assert inside.status_code == 409, inside.text
    assert inside.json()["detail"].endswith("With 30 min setup and 45 min turnaround it is in use until 12:45.")

    after = request("13:15", "14:00")
    assert after.status_code == 201, after.text
    booking_ids.append(after.json()["id"])
