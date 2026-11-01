"""S-90: restoring an original booking, TC-BOOKINGS-124..129.

The booking lookup and the overlap and period checks are stood in for here:
their own rules are S-75's and S-77's cases. These check what restoring asks
of them -- the venue's gap, the booking itself excluded -- and what it writes.
Updates run against a small in-memory table, so each filter is honoured.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .conftest import app, app_module, booking_row, database_module, table

O_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
R_ID = "11111111-1111-4111-8111-111111111111"
R2_ID = "22222222-2222-4222-8222-222222222222"
OTHER_ID = "33333333-3333-4333-8333-333333333333"
STUDIO_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
HALL_C = "cccccccc-0000-4000-8000-000000000000"
COORDINATOR = "c0c0c0c0-0000-4000-8000-000000000001"
STAFF = "abababab-abab-4bab-8bab-abababababab"
COOKIE = {"sb_access_token": "verified-token"}
GAP = "?setup_minutes=30&turnaround_minutes=45"
DECIDED = {"decided_by": STAFF, "decided_at": "2026-10-02T09:00:00+00:00"}

O = booking_row(id=O_ID, venue_id=STUDIO_B, status="confirmed", start_time="10:00:00",
                end_time="12:00:00", **DECIDED)
R = booking_row(id=R_ID, venue_id=HALL_C, venue_name="Hall C", status="pending",
                replaces_booking_id=O_ID, start_time="10:00:00", end_time="12:00:00")
R2 = {**R, "id": R2_ID, "status": "held", "held_by": STAFF,
      "held_at": "2026-10-03T09:00:00+00:00", "hold_expires_at": "2030-01-01T00:00:00+00:00"}
REQUESTED = {"restore_requested_at": "2026-11-01T02:00:00+00:00",
             "restore_requested_by": COORDINATOR}
BLOCK = {"id": "b1", "venue_name": "Studio B", "start_date": "2026-11-12",
         "start_time": "12:30:00", "end_date": "2026-11-12", "end_time": "14:00:00"}
CLASH = {"id": OTHER_ID, "status": "confirmed", "event_name": "Careers fair",
         "venue_name": "Studio B", "booking_date": "2026-11-12",
         "start_time": "13:00:00", "end_time": "14:00:00"}


class Update:
    """`.update(values)` with its filters, applied to the rows on execute."""

    def __init__(self, rows, values):
        self.rows, self.values, self.filters = rows, values, []

    def _keep(self, test):
        self.filters.append(test)
        return self

    def eq(self, column, value):
        return self._keep(lambda row: str(row.get(column)) == str(value))

    def in_(self, column, values):
        return self._keep(lambda row: row.get(column) in values)

    def is_(self, column, value):
        assert value == "null"
        return self._keep(lambda row: row.get(column) is None)

    @property
    def not_(self):
        update = self

        class Not:
            def is_(self, column, value):
                assert value == "null"
                return update._keep(lambda row: row.get(column) is not None)

        return Not()

    def execute(self):
        changed = [row for row in self.rows if all(test(row) for test in self.filters)]
        for row in changed:
            row.update(self.values)
        return SimpleNamespace(data=[dict(row) for row in changed])


@pytest.fixture
def rows(db, monkeypatch):
    """The bookings table, and the reads restoring makes of it."""
    store = []
    table(db).update.side_effect = lambda values: Update(store, values)
    monkeypatch.setattr(app_module, "_expire_holds", lambda db: [])
    monkeypatch.setattr(
        app_module, "_booking",
        lambda db, booking_id: next((dict(r) for r in store if r["id"] == str(booking_id)), None),
    )
    checks = SimpleNamespace(overlap=None, block=None, calls=[])

    def live_overlap(db, booking, gap=app_module.Gap()):
        checks.calls.append(("overlap", booking["id"], gap))
        return checks.overlap

    def block_over(db, booking, gap=app_module.Gap()):
        checks.calls.append(("block", booking["id"], gap))
        return checks.block

    monkeypatch.setattr(app_module, "_live_overlap", live_overlap)
    monkeypatch.setattr(app_module, "_block_over", block_over)
    return SimpleNamespace(store=store, checks=checks, put=store.extend)


@pytest.fixture
def signed_in():
    fake = MagicMock()
    app.dependency_overrides[database_module.get_auth] = lambda: fake

    def as_role(role, user_id):
        fake.auth.get_user.return_value.user = SimpleNamespace(id=user_id, app_metadata={"role": role})

    as_role("event_coordinator", COORDINATOR)
    yield as_role
    app.dependency_overrides.pop(database_module.get_auth, None)


def _row(rows, booking_id):
    return next(r for r in rows.store if r["id"] == booking_id)


def _ask(client):
    return client.post(f"/bookings/{O_ID}/restore-request{GAP}", cookies=COOKIE)


def _decide(client, decision):
    return client.post(f"/bookings/{O_ID}/restore-decision{GAP}",
                       json={"decision": decision}, cookies=COOKIE)


# --- TC-BOOKINGS-124 ------------------------------------------------------
def test_a_coordinator_asks_to_restore_an_original_whose_venue_is_free(client, rows, signed_in):
    rows.put([dict(O), dict(R)])
    before = datetime.now(timezone.utc)

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["restore_requested_by"] == COORDINATOR
    assert datetime.fromisoformat(body["restore_requested_at"]) >= before
    assert _row(rows, R_ID)["status"] == "pending"
    gap = app_module.Gap(30, 45)
    assert rows.checks.calls == [("overlap", O_ID, gap), ("block", O_ID, gap)]


# --- TC-BOOKINGS-125 ------------------------------------------------------
@pytest.mark.parametrize("clash, detail", [
    ("block", "Studio B is unavailable from 12 Nov 2026 12:30 to 12 Nov 2026 14:00."),
    ("overlap", "Studio B is already confirmed on 12 Nov 2026 from 13:00 to 14:00. "
                "With 30 min setup and 45 min turnaround it is in use until 14:45."),
])
def test_a_restore_is_refused_while_the_venue_is_not_free_for_the_whole_window(
    client, rows, signed_in, clash, detail
):
    rows.put([dict(O)])
    if clash == "block":
        rows.checks.block = BLOCK
    else:
        rows.checks.overlap = CLASH

    response = _ask(client)

    assert (response.status_code, response.json()) == (409, {"detail": detail})
    assert _row(rows, O_ID).get("restore_requested_at") is None


def test_a_booking_just_outside_the_gap_does_not_stop_a_restore(client, rows, signed_in):
    # The overlap check found nothing: 13:30 is beyond 12:00 + 45 + 30.
    rows.put([dict(O)])
    assert _ask(client).status_code == 200


# --- TC-BOOKINGS-126 ------------------------------------------------------
@pytest.mark.parametrize("settled", ["replaced", "rejected", "pending"])
def test_only_a_live_original_without_a_request_can_be_restored(client, rows, signed_in, settled):
    rows.put([{**O, "status": settled}])
    response = _ask(client)
    assert (response.status_code, response.json()) == (
        409, {"detail": "Only a held or confirmed booking can be restored"}
    )


def test_a_second_restore_request_is_refused(client, rows, signed_in):
    rows.put([{**O, **REQUESTED}])
    response = _ask(client)
    assert (response.status_code, response.json()) == (
        409, {"detail": "A restore has already been requested for this booking"}
    )


def test_restore_requests_need_a_known_booking_and_a_coordinator(client, rows, signed_in):
    assert (_ask(client).status_code, _ask(client).json()) == (404, {"detail": "Booking not found"})
    rows.put([dict(O)])
    signed_in("venue_staff", STAFF)
    assert _ask(client).status_code == 403
    assert _row(rows, O_ID).get("restore_requested_at") is None


# --- TC-BOOKINGS-127 ------------------------------------------------------
def test_confirming_a_restore_withdraws_the_replacement_and_resolves_the_original(
    client, rows, signed_in
):
    rows.put([{**O, **REQUESTED}, dict(R), dict(R2), {**R, "id": OTHER_ID, "status": "rejected",
                                                      "decision_reason": "Booked", **DECIDED}])
    signed_in("venue_staff", STAFF)

    response = _decide(client, "approved")

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(row["id"] for row in body["withdrawn"]) == [R_ID, R2_ID]
    for replacement in (R_ID, R2_ID):
        row = _row(rows, replacement)
        assert row["status"] == "withdrawn" and row["withdrawn_at"]
    # A replacement already decided is left as it was.
    assert _row(rows, OTHER_ID)["status"] == "rejected"
    original = body["booking"]
    assert original["status"] == "confirmed"
    assert original["restore_requested_at"] is None and original["restore_requested_by"] is None
    assert original["alternative_resolved_by"] == COORDINATOR
    assert original["alternative_resolution_note"] == "Restored to the original venue"
    assert original["alternative_resolved_at"]
    assert rows.checks.calls[0] == ("overlap", O_ID, app_module.Gap(30, 45))


# --- TC-BOOKINGS-128 ------------------------------------------------------
@pytest.mark.parametrize("case, detail", [
    ("block", "Studio B is unavailable from 12 Nov 2026 12:30 to 12 Nov 2026 14:00."),
    ("overlap", "Can't restore this booking: it overlaps Careers fair (confirmed), which occupies "
                "Studio B on 12 Nov 2026 from 12:30 to 14:45 "
                "(event 13:00–14:00, 30 min setup, 45 min turnaround)."),
    ("no request", "There is no restore request to decide for this booking"),
    ("replaced", "Only a held or confirmed booking can be restored"),
])
def test_a_restore_decision_is_checked_again(client, rows, signed_in, case, detail):
    original = {**O, **REQUESTED}
    if case == "no request":
        original = dict(O)
    if case == "replaced":
        original = {**O, "status": "replaced", "replaced_at": "2026-11-01T03:00:00+00:00"}
    rows.put([original, dict(R)])
    rows.checks.block = BLOCK if case == "block" else None
    rows.checks.overlap = CLASH if case == "overlap" else None
    signed_in("venue_staff", STAFF)

    response = _decide(client, "approved")

    assert (response.status_code, response.json()) == (409, {"detail": detail})
    assert _row(rows, R_ID)["status"] == "pending"
    assert _row(rows, O_ID).get("alternative_resolution_note") is None


def test_declining_a_restore_only_clears_the_request(client, rows, signed_in):
    rows.put([{**O, **REQUESTED}, dict(R)])
    signed_in("venue_staff", STAFF)

    response = _decide(client, "declined")

    assert response.status_code == 200, response.text
    assert response.json()["withdrawn"] == []
    original = response.json()["booking"]
    assert original["restore_requested_at"] is None
    assert original["alternative_resolution_note"] is None
    assert _row(rows, R_ID)["status"] == "pending"
    assert rows.checks.calls == []


def test_only_venue_staff_decide_a_restore(client, rows, signed_in):
    rows.put([{**O, **REQUESTED}, dict(R)])
    assert _decide(client, "approved").status_code == 403
    signed_in("venue_staff", STAFF)
    assert _decide(client, "maybe").status_code == 422
    assert _row(rows, R_ID)["status"] == "pending"


# --- TC-BOOKINGS-129 ------------------------------------------------------
def test_venue_staff_list_the_restore_requests_waiting_for_them(client, db, monkeypatch):
    monkeypatch.setattr(app_module, "_expire_holds", lambda db: [])
    query = table(db).select.return_value
    query.not_.is_.return_value = query
    query.order.return_value = query
    query.execute.return_value = SimpleNamespace(data=[{**O, **REQUESTED}])

    response = client.get("/bookings?restore_requested=true")

    assert response.status_code == 200, response.text
    [row] = response.json()
    assert row["id"] == O_ID
    assert row["restore_requested_by"] == COORDINATOR
    assert row["withdrawn_at"] is None
    query.not_.is_.assert_called_once_with("restore_requested_at", "null")
    query.order.assert_called_once_with("restore_requested_at")
