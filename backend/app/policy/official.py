"""Source-backed factual measurements and post-model eligibility checks.

Measurement extraction never carries a verdict. Eligibility checks can only withhold
an unsafe model decision for review; they never compute a replacement remedy.
"""
from datetime import datetime
from typing import Any


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def factual_values(facts, filed_at=None):
    ride, route, fare = [facts.get(k) or {} for k in ('ride', 'route', 'fare')]
    values = {k: ride.get(k) for k in ('service_tier', 'accepted_at', 'scheduled_at',
              'cancellation_timestamp', 'cancellation_actor', 'completed_at')}
    values['arrival_at'] = route.get('driver_arrival_at')
    values['driver_waited_seconds'] = ride.get('driver_waited_seconds')
    if values['driver_waited_seconds'] is None:
        values['driver_waited_seconds'] = route.get('driver_wait_seconds')
    values['waiting_fare_cents'] = fare.get('waiting_fare_cents')
    values['arrival_button_recorded'] = False
    for event in facts.get('app_events') or []:
        # Unverified events must not establish decisive facts.
        if event.get('verification_status') != 'verified':
            continue
        kind = str(event.get('event_type', '')).lower()
        at = event.get('event_at')
        if kind in ('matched', 'driver_matched', 'accepted'):
            values['accepted_at'] = values['accepted_at'] or at
        elif kind in ('im_here', 'i_am_here', 'driver_arrived'):
            values['arrival_button_recorded'] = True
            values['arrival_at'] = values['arrival_at'] or at
        elif kind in ('rider_cancelled', 'driver_cancelled'):
            values['cancellation_actor'] = kind.split('_')[0]
            values['cancellation_timestamp'] = values['cancellation_timestamp'] or at
    def duration(end, start):
        a,b = timestamp(end), timestamp(start)
        return (a-b).total_seconds() if a and b else None
    values['seconds_after_matching'] = duration(values['cancellation_timestamp'], values['accepted_at'])
    values['seconds_before_schedule_at_match'] = duration(values['scheduled_at'], values['accepted_at'])
    values['seconds_before_schedule'] = duration(values['scheduled_at'], values['cancellation_timestamp'])
    end = values['cancellation_timestamp'] or ride.get('pickup_at')
    observed_wait = duration(end, values['arrival_at'])
    if observed_wait is not None:
        values['driver_waited_seconds'] = observed_wait
    trip_end = values['cancellation_timestamp'] or values['completed_at']
    age = duration(filed_at, trip_end)
    values['days_since_trip'] = age / 86400 if age is not None else None
    return {k:v for k,v in values.items() if v is not None}
