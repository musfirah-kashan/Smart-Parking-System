"""Phase 12: Admin + Analytics 2.0
Occupancy chart, revenue chart, popular slots (heap top-N), peak hours,
and a JSON endpoint so slot status updates live without reloading."""
import heapq
from collections import Counter, defaultdict
from datetime import datetime

from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from models import ParkingRecord, ParkingSlot, Payment, WaitingEntry
from reports import admin_only, revenue_by_day

analytics_bp = Blueprint("analytics", __name__)

STATUSES = ["available", "occupied", "reserved", "maintenance"]


def slot_snapshot():
    slots = ParkingSlot.query.order_by(ParkingSlot.slot_number).all()
    counts = Counter(s.status for s in slots)
    return slots, {s: counts.get(s, 0) for s in STATUSES}


@analytics_bp.route("/api/slots")
@login_required
def api_slots():
    """Polled every few seconds by the analytics page (and any other page)."""
    slots, counts = slot_snapshot()
    total = len(slots)
    return jsonify({
        "slots": [
            {"id": s.id, "slot_number": s.slot_number,
             "slot_type": s.slot_type, "status": s.status}
            for s in slots
        ],
        "counts": counts,
        "occupancy": round(100 * counts["occupied"] / total, 1) if total else 0,
        "updated": datetime.now().strftime("%I:%M:%S %p"),
    })


@analytics_bp.route("/admin/analytics")
@admin_only
def analytics():
    slots, counts = slot_snapshot()
    total = len(slots)

    per_slot = defaultdict(int)
    per_hour = [0] * 24
    for rec in ParkingRecord.query.all():
        per_slot[rec.slot_id] += 1
        if rec.entry_time:
            per_hour[rec.entry_time.hour] += 1

    by_id = {s.id: s for s in slots}
    top = heapq.nlargest(5, per_slot.items(), key=lambda kv: kv[1])
    popular = [
        {"slot": by_id[sid].slot_number, "count": c}
        for sid, c in top if sid in by_id
    ]
    peak_hour = max(range(24), key=lambda h: per_hour[h]) if any(per_hour) else None

    revenue = revenue_by_day(14)
    paid_total = sum(p.amount or 0 for p in Payment.query.filter_by(status="paid"))

    return render_template(
        "analytics.html",
        statuses=STATUSES, counts=counts, total=total,
        occupancy=round(100 * counts["occupied"] / total, 1) if total else 0,
        popular=popular, per_hour=per_hour, peak_hour=peak_hour,
        rev_labels=[d for d, _ in revenue], rev_values=[v for _, v in revenue],
        paid_total=paid_total,
        waiting=WaitingEntry.query.filter_by(status="waiting").count(),
    )
