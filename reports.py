"""Phase 11: Reports & Payments 2.0
Revenue reports, daily/weekly/monthly history, payment status list,
advanced filters and CSV export.  Registered as a Blueprint so app.py
barely changes (fewer merge conflicts)."""
import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, Response, abort, render_template, request
from flask_login import current_user, login_required

from models import db, ParkingRecord, ParkingSlot, Payment, Vehicle
from dsa.sorting import merge_sort

reports_bp = Blueprint("reports", __name__)

PAYMENT_METHODS = ["Cash", "Card", "JazzCash", "Easypaisa"]
PERIODS = ("daily", "weekly", "monthly")


def admin_only(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ---------------- helpers ----------------

def parse_date(raw):
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def payment_rows(status="", method="", q="", slot="",
                 start=None, end=None, own_only=False):
    """One list of dicts used by the report, payments page, export and charts.
    'when' = paid_at, or the exit time for old payments that have no paid_at."""
    query = (
        db.session.query(Payment, ParkingRecord, Vehicle)
        .join(ParkingRecord, Payment.record_id == ParkingRecord.id)
        .join(Vehicle, ParkingRecord.vehicle_id == Vehicle.id)
    )
    if own_only:
        query = query.filter(Vehicle.user_id == current_user.id)
    if status:
        query = query.filter(Payment.status == status)
    if method:
        query = query.filter(Payment.method == method)
    if q:
        query = query.filter(Vehicle.vehicle_number.ilike(f"%{q}%"))

    rows = []
    for pay, rec, veh in query.all():
        when = pay.paid_at or rec.exit_time
        if start and (when is None or when < start):
            continue
        if end and (when is None or when >= end):
            continue
        slot_obj = db.session.get(ParkingSlot, rec.slot_id)
        if slot and (
            slot_obj is None or slot.lower() not in slot_obj.slot_number.lower()
        ):
            continue
        rows.append({
            "payment": pay,
            "record": rec,
            "vehicle": veh,
            "slot": slot_obj,
            "when": when,
            "amount": pay.amount or 0,
            "status": pay.status,
            "method": pay.method or "",
        })
    return rows


def period_key(when, period):
    if period == "weekly":
        iso = when.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if period == "monthly":
        return when.strftime("%Y-%m")
    return when.strftime("%Y-%m-%d")


def revenue_by_period(rows, period="daily"):
    """Group rows by day / week / month. Returns [(key, {paid, pending, count})]."""
    totals = defaultdict(lambda: {"paid": 0, "pending": 0, "count": 0})
    for r in rows:
        if r["when"] is None:
            continue
        bucket = totals[period_key(r["when"], period)]
        bucket["count"] += 1
        if r["status"] == "paid":
            bucket["paid"] += r["amount"]
        else:
            bucket["pending"] += r["amount"]
    return sorted(totals.items())


def revenue_by_day(days=14):
    """[(label, paid_amount)] for the last N days (zero-filled). Phase 12 chart uses this."""
    today = datetime.now().date()
    first = today - timedelta(days=days - 1)
    rows = payment_rows(
        status="paid", start=datetime.combine(first, datetime.min.time())
    )
    totals = defaultdict(float)
    for r in rows:
        totals[r["when"].date()] += r["amount"]
    out = []
    for i in range(days):
        d = first + timedelta(days=i)
        out.append((d.strftime("%d %b"), totals.get(d, 0)))
    return out


def filters_from_request():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    end = parse_date(date_to)
    return {
        "status": request.args.get("status", ""),
        "method": request.args.get("method", ""),
        "q": request.args.get("q", "").strip(),
        "slot": request.args.get("slot", "").strip(),
        "date_from": date_from,
        "date_to": date_to,
        "start": parse_date(date_from),
        "end": end + timedelta(days=1) if end else None,   # 'to' date is inclusive
    }


SORT_FIELDS = {
    "date": lambda r: r["when"] or datetime.min,
    "amount": lambda r: r["amount"],
    "vehicle": lambda r: r["vehicle"].vehicle_number,
    "status": lambda r: r["status"],
}


# ---------------- routes ----------------

@reports_bp.route("/reports")
@admin_only
def revenue_report():
    period = request.args.get("period", "daily")
    if period not in PERIODS:
        period = "daily"
    f = filters_from_request()
    rows = payment_rows(start=f["start"], end=f["end"])

    periods = revenue_by_period(rows, period)
    periods.reverse()                       # newest first

    by_method = defaultdict(lambda: {"amount": 0, "count": 0})
    for r in rows:
        if r["status"] == "paid":
            label = r["method"] or "Not recorded"
            by_method[label]["amount"] += r["amount"]
            by_method[label]["count"] += 1

    total_paid = sum(r["amount"] for r in rows if r["status"] == "paid")
    total_pending = sum(r["amount"] for r in rows if r["status"] != "paid")

    return render_template(
        "reports.html",
        period=period, periods=periods, by_method=sorted(by_method.items()),
        total_paid=total_paid, total_pending=total_pending, count=len(rows),
        date_from=f["date_from"], date_to=f["date_to"],
    )


@reports_bp.route("/payments")
@login_required
def payments_list():
    f = filters_from_request()
    sort_by = request.args.get("sort", "date")
    order = request.args.get("order", "desc")
    if sort_by not in SORT_FIELDS:
        sort_by = "date"
    if order not in ("asc", "desc"):
        order = "desc"

    rows = payment_rows(
        status=f["status"], method=f["method"], q=f["q"], slot=f["slot"],
        start=f["start"], end=f["end"], own_only=current_user.role != "admin",
    )
    rows = merge_sort(rows, key=SORT_FIELDS[sort_by], reverse=(order == "desc"))

    total_paid = sum(r["amount"] for r in rows if r["status"] == "paid")
    total_pending = sum(r["amount"] for r in rows if r["status"] != "paid")
    return render_template(
        "payments.html", rows=rows, methods=PAYMENT_METHODS,
        total_paid=total_paid, total_pending=total_pending,
        sort_by=sort_by, order=order, f=f,
    )


@reports_bp.route("/payments/export.csv")
@login_required
def export_csv():
    f = filters_from_request()
    is_admin = current_user.role == "admin"
    kind = request.args.get("kind", "payments")
    out = io.StringIO()
    writer = csv.writer(out)

    if kind == "summary" and is_admin:
        period = request.args.get("period", "daily")
        if period not in PERIODS:
            period = "daily"
        rows = payment_rows(start=f["start"], end=f["end"])
        writer.writerow([period.capitalize(), "Paid (Rs)", "Pending (Rs)", "Payments"])
        for key, b in revenue_by_period(rows, period):
            writer.writerow([key, f"{b['paid']:.0f}", f"{b['pending']:.0f}", b["count"]])
        filename = f"revenue_{period}.csv"
    else:
        rows = payment_rows(
            status=f["status"], method=f["method"], q=f["q"], slot=f["slot"],
            start=f["start"], end=f["end"], own_only=not is_admin,
        )
        rows = merge_sort(rows, key=SORT_FIELDS["date"], reverse=True)
        writer.writerow([
            "Payment ID", "Vehicle", "Slot", "Entry", "Exit",
            "Amount (Rs)", "Status", "Method", "Date",
        ])
        for r in rows:
            rec = r["record"]
            writer.writerow([
                r["payment"].id,
                r["vehicle"].vehicle_number,
                r["slot"].slot_number if r["slot"] else "",
                rec.entry_time.strftime("%Y-%m-%d %H:%M") if rec.entry_time else "",
                rec.exit_time.strftime("%Y-%m-%d %H:%M") if rec.exit_time else "",
                f"{r['amount']:.0f}", r["status"], r["method"],
                r["when"].strftime("%Y-%m-%d %H:%M") if r["when"] else "",
            ])
        filename = "payments.csv"

    return Response(
        out.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
