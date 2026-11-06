"""Reservation logic : booking, overlap check and overstay.

A slot is free for a time window only if no ACTIVE booking overlaps it.
Two windows overlap when:  new_start < old_end  and  old_start < new_end.

Among the free slots we reuse Member 4's pipeline: the vehicle's type and
priority give the suitable slot types, then a Min Heap (key = distance)
gives the nearest free slot.

Overstay: a vehicle that leaves after its booked time ended pays extra.
"""
import math
from datetime import timedelta

from models import ParkingSlot, Booking
from .hash_table import HashTable
from .min_heap import MinHeap
from .parking_engine import pick_best_slot, EARLY_ARRIVAL_GRACE

OVERSTAY_RATE_PER_HOUR = 100                 # Rs. per extra hour
# Bookings that still block their time window: waiting (active) or checked in (used).
# 'completed' (vehicle already left) and 'cancelled' free the slot again.
BLOCKING_STATUSES = ("active", "used")
# Bookings that can still be compared with a parking record for overstay.
OVERSTAY_STATUSES = ("active", "used", "completed")


def booking_end(booking):
    return booking.start_time + timedelta(hours=booking.duration_hours)


def overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def free_slots_for(start, hours):
    """Every slot with no overlapping active booking (maintenance slots skipped)."""
    end = start + timedelta(hours=hours)
    busy = set()
    for b in Booking.query.filter(Booking.status.in_(BLOCKING_STATUSES)).all():
        if overlaps(start, end, b.start_time, booking_end(b)):
            busy.add(b.slot_id)
    return [
        s for s in ParkingSlot.query.all()
        if s.status != "maintenance" and s.id not in busy
    ]


def vehicle_is_busy(vehicle_id, start, hours):
    """True if this vehicle already has a booking overlapping the window."""
    end = start + timedelta(hours=hours)
    for b in Booking.query.filter(
        Booking.vehicle_id == vehicle_id, Booking.status.in_(BLOCKING_STATUSES)
    ).all():
        if overlaps(start, end, b.start_time, booking_end(b)):
            return True
    return False


def reserve_slot(vehicle, start, hours, trace=None):
    """Returns the best free slot for the window (or None)."""
    groups = {}
    for s in free_slots_for(start, hours):
        groups.setdefault((s.slot_type or "normal").lower(), []).append(
            ((s.distance or 0.0, s.slot_number), s.id)
        )
    heaps = {t: MinHeap.build(entries) for t, entries in groups.items()}
    return pick_best_slot(vehicle, heaps, trace)


# ---------------------------------------------------------------- overstay

def bookings_by_vehicle():
    """Hash table: vehicle id -> list of its active bookings (O(1) lookup)."""
    table = HashTable()
    for b in Booking.query.filter(Booking.status.in_(OVERSTAY_STATUSES)).all():
        items = table.get(b.vehicle_id)
        if items is None:
            items = []
            table.put(b.vehicle_id, items)
        items.append(b)
    return table


def overstay_info(record, table):
    """Compare a finished parking with the booking it belongs to.

    A parking record belongs to a booking when it is the same vehicle and the
    vehicle arrived inside the booked window (15 minutes early is allowed).
    Returns None when there is no such booking.
    """
    for booking in table.get(record.vehicle_id, []):
        end = booking_end(booking)
        if booking.start_time - EARLY_ARRIVAL_GRACE <= record.entry_time <= end:
            late_seconds = (record.exit_time - end).total_seconds()
            if late_seconds <= 0:
                return {"booking": booking, "late_minutes": 0, "extra_fee": 0}
            return {
                "booking": booking,
                "late_minutes": math.ceil(late_seconds / 60),
                "extra_fee": math.ceil(late_seconds / 3600) * OVERSTAY_RATE_PER_HOUR,
            }
    return None