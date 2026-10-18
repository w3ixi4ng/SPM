"""TC-E2E-240 -- required hold expiry, notice, and immediate availability."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from playwright.sync_api import expect

from .conftest import open_request, requires_env
from .test_tentative_hold import add_booking
from .test_venue_availability import add_event, add_venue, d, day_cell, day_detail, open_calendar, show_month

pytestmark = requires_env


def test_tentative_hold_expiry_is_visible_notified_and_releases_the_slot(
    admin, page, make_user, sign_in,
):
    coordinator = make_user('event_coordinator')
    staff = make_user('venue_staff')
    organiser = make_user('event_organiser')
    venue = add_venue(admin, staff, uuid.uuid4().hex[:6])
    event = add_event(admin, organiser, coordinator, 'S81', d(5))
    booking = add_booking(admin, event, venue, coordinator)

    sign_in(staff)
    page.wait_for_url(re.compile(r'/dashboard/venue-staff$'), timeout=30000)
    open_request(page, event['name'])
    page.get_by_role('button', name='Place hold').click()
    expect(page.get_by_role('alert')).to_contain_text('Choose when the tentative hold expires')
    page.get_by_label('Hold expiry').fill('2099-01-01T12:00')
    page.get_by_role('button', name='Place hold').click()
    expect(page.get_by_role('button', name='Release hold')).to_be_visible(timeout=30000)
    expect(page.get_by_text(re.compile(r'Expires .* Singapore time'))).to_be_visible()

    open_calendar(page, venue['name'], '/dashboard/venue-staff')
    show_month(page, d(5))
    day_cell(page, d(5)).click()
    expect(day_detail(page, d(5))).to_contain_text('Tentatively held 09:00', timeout=30000)

    page.get_by_role('link', name='Back to dashboard').click()
    page.get_by_role('button', name='Sign out').click()
    page.wait_for_url(re.compile(r'/login$'), timeout=30000)
    sign_in(coordinator)
    page.wait_for_url(re.compile(r'/dashboard/event-coordinator$'), timeout=30000)
    inbox = page.get_by_role('region', name='Notifications')
    expect(inbox).to_contain_text('tentative hold', timeout=30000)
    expect(inbox).to_contain_text(venue['name'])

    admin.schema('bookings').table('bookings').update({
        'hold_expires_at': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    }).eq('id', booking['id']).execute()
    open_calendar(page, venue['name'], '/dashboard/event-coordinator')
    show_month(page, d(5))
    day_cell(page, d(5)).click()
    expect(day_detail(page, d(5))).to_contain_text('Available', timeout=30000)

    stored = admin.schema('bookings').table('bookings').select(
        'status,hold_release_reason'
    ).eq('id', booking['id']).execute().data[0]
    assert stored == {'status': 'pending', 'hold_release_reason': 'expired'}
