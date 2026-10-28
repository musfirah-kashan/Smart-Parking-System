"""Smart Parking engine - glues the data structures to the database.

Phase 5  ->  SearchIndex      (Hash Tables)
Phase 6  ->  best slot        (Min Heap per slot type)
             waiting list     (Priority Queue + FIFO Queue)
             smart_park()     (the full "final smart allocation" pipeline)

The database stays the single source of truth. The data structures are
rebuilt from it when needed, so a server restart never loses anything.
"""
import re
import threading
import time
from datetime import datetime

from sqlalchemy import event

from models import db, User, Vehicle, ParkingSlot, ParkingRecord, WaitingEntry
from . import HashTable, MinHeap, FifoQueue, PriorityQueue

# ---------------------------------------------------------------- constants

# Smaller number = served first (same order as the project plan)
PRIORITY_RANK = {"Emergency": 0, "Disabled": 1, "EV": 2, "VIP": 3, "Normal": 4}
PRIORITY_LEVELS = list(PRIORITY_RANK)

# Only an admin may give these (anyone could otherwise claim them)
ADMIN_ONLY_PRIORITIES = ("Emergency", "VIP")

SLOT_TYPES = ["normal", "bike", "handicapped", "ev", "vip", "emergency"]

# "Find suitable slots": slot types each priority class may use, best first
SLOT_PREFERENCE = {
    "Emergency": ["emergency", "normal", "vip", "handicapped", "ev"],
    "Disabled": ["handicapped", "normal"],
    "EV": ["ev", "normal"],
    "VIP": ["vip", "normal"],
    "Normal": ["normal"],
}


def normalize_plate(text):
    """'abc-123' / 'ABC 123' / 'abc123'  ->  'ABC123' (the hash key)."""
    return re.sub(r"[^A-Za-z0-9]", "", text or "").upper()


def suitable_slot_types(vehicle_type, priority):
    """Step 'Check vehicle type' + 'Find suitable slots'."""
    types = list(SLOT_PREFERENCE.get(priority, SLOT_PREFERENCE["Normal"]))
    if (vehicle_type or "").lower() == "bike":
        types.insert(0, "bike")      # bikes prefer small bike bays
    return types                     # cars never get "bike" slots


# ------------------------------------------------------ Phase 5: hash search

class SearchIndex:
    """Hash tables for O(1) lookup.

        vehicles : plate         -> {vehicle_id, slot_id, record_id}
        slots    : slot number   -> slot_id
        emails   : email         -> user_id
        phones   : phone number  -> user_id

    The index is rebuilt (O(n)) only after the database changed. Between
    changes every search is a single O(1) hash lookup.
    """

    def __init__(self):
        self.vehicles = HashTable()
        self.slots = HashTable()
        self.emails = HashTable()
        self.phones = HashTable()
        self.dirty = True
        self.rebuilds = 0
        self._lock = threading.Lock()

    def mark_dirty(self, *_args, **_kwargs):
        self.dirty = True

    def ensure_fresh(self):
        if not self.dirty:
            return
        with self._lock:
            if not self.dirty:
                return
            self.dirty = False          # set first: a change during rebuild re-dirties it
            self._rebuild()

    def _rebuild(self):
        vehicles, slots = HashTable(), HashTable()
        emails, phones = HashTable(), HashTable()

        active = {}
        for rec in ParkingRecord.query.filter(ParkingRecord.exit_time.is_(None)).all():
            active[rec.vehicle_id] = rec

        for v in Vehicle.query.all():
            rec = active.get(v.id)
            vehicles.put(normalize_plate(v.vehicle_number), {
                "vehicle_id": v.id,
                "slot_id": rec.slot_id if rec else None,
                "record_id": rec.id if rec else None,
            })
        for s in ParkingSlot.query.all():
            slots.put(s.slot_number.upper(), s.id)
        for u in User.query.all():
            emails.put((u.email or "").lower(), u.id)
            if u.phone:
                phones.put(re.sub(r"\D", "", u.phone), u.id)

        self.vehicles, self.slots = vehicles, slots
        self.emails, self.phones = emails, phones
        self.rebuilds += 1

    # ----- searches (each returns (results, info)) -----
    def search_vehicle(self, text):
        self.ensure_fresh()
        key = normalize_plate(text)
        t0 = time.perf_counter_ns()
        hit = self.vehicles.get(key)
        probes = self.vehicles.last_probes
        elapsed = (time.perf_counter_ns() - t0) / 1e6
        if hit is not None:
            return [hit], {"method": "Hash table lookup", "big_o": "O(1)",
                           "steps": probes, "ms": elapsed}
        # not an exact plate -> fall back to a partial match
        t0 = time.perf_counter_ns()
        found, scanned = [], 0
        if key:
            for k, v in self.vehicles.items():
                scanned += 1
                if key in k:
                    found.append(v)
        elapsed = (time.perf_counter_ns() - t0) / 1e6
        return found, {"method": "Partial match (linear scan)", "big_o": "O(n)",
                       "steps": scanned, "ms": elapsed}

    def search_slot(self, text):
        self.ensure_fresh()
        key = (text or "").strip().upper()
        t0 = time.perf_counter_ns()
        slot_id = self.slots.get(key)
        probes = self.slots.last_probes
        elapsed = (time.perf_counter_ns() - t0) / 1e6
        if slot_id is not None:
            return [slot_id], {"method": "Hash table lookup", "big_o": "O(1)",
                               "steps": probes, "ms": elapsed}
        t0 = time.perf_counter_ns()
        found, scanned = [], 0
        if key:
            for k, v in self.slots.items():
                scanned += 1
                if key in k:
                    found.append(v)
        elapsed = (time.perf_counter_ns() - t0) / 1e6
        return found, {"method": "Partial match (linear scan)", "big_o": "O(n)",
                       "steps": scanned, "ms": elapsed}

    def search_user(self, text):
        self.ensure_fresh()
        text = (text or "").strip()
        t0 = time.perf_counter_ns()
        uid = self.emails.get(text.lower())
        probes = self.emails.last_probes
        if uid is None and re.sub(r"\D", "", text):
            uid = self.phones.get(re.sub(r"\D", "", text))
            probes += self.phones.last_probes
        elapsed = (time.perf_counter_ns() - t0) / 1e6
        if uid is not None:
            return [uid], {"method": "Hash table lookup (email / phone)",
                           "big_o": "O(1)", "steps": probes, "ms": elapsed}
        # names are not unique keys -> scan
        t0 = time.perf_counter_ns()
        found, scanned = [], 0
        needle = text.lower()
        if needle:
            for u in User.query.order_by(User.id).all():
                scanned += 1
                if needle in (u.name or "").lower():
                    found.append(u.id)
        elapsed = (time.perf_counter_ns() - t0) / 1e6
        return found, {"method": "Name search (linear scan)", "big_o": "O(n)",
                       "steps": scanned, "ms": elapsed}


search_index = SearchIndex()

# Any change to these tables invalidates the index automatically.
for _model in (User, Vehicle, ParkingSlot, ParkingRecord):
    for _evt in ("after_insert", "after_update", "after_delete"):
        event.listen(_model, _evt, search_index.mark_dirty)


# ---------------------------------------------- Phase 6: min heap + slots

def build_slot_heaps():
    """One min-heap per slot type, holding only AVAILABLE slots.

    key   = (distance, slot_number)   -> nearest slot is always on top
    value = slot id
    Built with Floyd's heapify in O(n).
    """
    groups = {}
    for s in ParkingSlot.query.filter_by(status="available").all():
        groups.setdefault((s.slot_type or "normal").lower(), []).append(
            ((s.distance or 0.0, s.slot_number), s.id)
        )
    return {t: MinHeap.build(entries) for t, entries in groups.items()}


def pick_best_slot(vehicle, heaps, trace=None):
    """Vehicle type + priority -> suitable slot types -> min heap -> best slot.

    Pops the winner out of `heaps`, so calling it again for the next vehicle
    can never hand out the same slot twice.
    """
    trace = trace if trace is not None else []
    types = suitable_slot_types(vehicle.vehicle_type, vehicle.priority or "Normal")
    trace.append(f"{vehicle.vehicle_type} / {vehicle.priority or 'Normal'} "
                 f"-> suitable slot types: {', '.join(types)}")
    for t in types:
        heap = heaps.get(t)
        if heap is None or heap.is_empty():
            trace.append(f"'{t}' heap is empty - skip")
            continue
        (distance, number), slot_id = heap.pop_min()      # extractMin()
        trace.append(f"'{t}' heap -> extractMin() = {number} ({distance:g} m)")
        return db.session.get(ParkingSlot, slot_id)
    trace.append("no suitable slot is free")
    return None


# ---------------------------------------------- Phase 6: waiting queue

def waiting_entries():
    return (WaitingEntry.query.filter_by(status="waiting")
            .order_by(WaitingEntry.id).all())


def waiting_vehicle_ids():
    return {e.vehicle_id for e in waiting_entries()}


def build_waiting_pq():
    """Priority queue of waiting entries (rank first, then arrival order)."""
    pq = PriorityQueue()
    for e in waiting_entries():
        v = db.session.get(Vehicle, e.vehicle_id)
        if v is None:
            continue
        pq.push(e, PRIORITY_RANK.get(v.priority or "Normal", 4), order=e.id)
    return pq


def build_waiting_fifo():
    """Plain FIFO view (arrival order only) - used to compare with the priority queue."""
    q = FifoQueue()
    for e in waiting_entries():
        q.enqueue(e)
    return q


def queue_position(entry):
    """1-based position of an entry in the PRIORITY order."""
    for i, (_, e) in enumerate(build_waiting_pq().ordered(), start=1):
        if e.id == entry.id:
            return i
    return None


def cancel_waiting(entry):
    entry.status = "cancelled"
    db.session.commit()


def _park(vehicle, slot, when=None):
    record = ParkingRecord(vehicle_id=vehicle.id, slot_id=slot.id,
                           entry_time=when or datetime.now())
    slot.status = "occupied"
    db.session.add(record)
    return record


def assign_waiting_vehicles():
    """Call this whenever a slot becomes free.

    Takes waiting vehicles in PRIORITY order and gives each the nearest
    suitable slot. A vehicle that cannot be served right now (no suitable
    slot type is free) goes to a FIFO `deferred` queue and keeps waiting, so
    it does not block the vehicles behind it.

    Returns a list of (vehicle, slot) that were parked.
    """
    pq = build_waiting_pq()
    if pq.is_empty():
        return []

    heaps = build_slot_heaps()
    parked_ids = {r.vehicle_id for r in
                  ParkingRecord.query.filter(ParkingRecord.exit_time.is_(None)).all()}
    deferred = FifoQueue()
    done = []

    while not pq.is_empty():
        entry = pq.pop()
        vehicle = db.session.get(Vehicle, entry.vehicle_id)
        if vehicle is None or vehicle.id in parked_ids:
            entry.status = "cancelled"
            continue
        slot = pick_best_slot(vehicle, heaps)
        if slot is None:
            deferred.enqueue(entry)         # still waiting
            continue
        _park(vehicle, slot)
        entry.status = "assigned"
        entry.assigned_at = datetime.now()
        parked_ids.add(vehicle.id)
        done.append((vehicle, slot))

    db.session.commit()
    return done


# ---------------------------------------------- the full smart pipeline

def smart_park(vehicle):
    """Vehicle arrives -> check type -> suitable slots -> Min Heap -> best slot
    -> assign. If nothing is free the vehicle joins the Priority Queue.

    Returns dict: status ('parked' | 'queued'), slot, entry, position, trace.
    """
    trace = ["Vehicle arrives: " + vehicle.vehicle_number]
    heaps = build_slot_heaps()
    slot = pick_best_slot(vehicle, heaps, trace)

    if slot is not None:
        _park(vehicle, slot)
        db.session.commit()
        return {"status": "parked", "slot": slot, "trace": trace}

    entry = WaitingEntry(vehicle_id=vehicle.id, status="waiting",
                         joined_at=datetime.now())
    db.session.add(entry)
    db.session.commit()
    trace.append("parking full for this vehicle -> added to the Priority Queue")
    return {"status": "queued", "entry": entry,
            "position": queue_position(entry), "trace": trace}