import math
import os
import re
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, Vehicle, ParkingSlot, ParkingRecord, Payment, WaitingEntry
import models
from dsa.parking_engine import (
    ADMIN_ONLY_PRIORITIES,
    PRIORITY_LEVELS,
    SLOT_PREFERENCE,
    SLOT_TYPES,
    assign_waiting_vehicles,
    build_slot_heaps,
    build_waiting_fifo,
    build_waiting_pq,
    cancel_waiting,
    queue_position,
    search_index,
    smart_park,
    waiting_vehicle_ids,
)


app = Flask(__name__)

os.makedirs(app.instance_path, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///parking.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change-this-secret-key"

db.init_app(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def ensure_schema():
    """Old parking.db files do not have the new Vehicle.priority column yet.
    Add it automatically so nobody has to delete their database."""
    columns = [c["name"] for c in inspect(db.engine).get_columns("vehicle")]
    if "priority" not in columns:
        with db.engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE vehicle ADD COLUMN priority VARCHAR(20) DEFAULT 'Normal'"
            ))


# ---------------- DEFAULT ADMIN (fixed login) ----------------
DEFAULT_ADMIN_NAME = "Admin"
DEFAULT_ADMIN_EMAIL = "admin@gmail.com"
DEFAULT_ADMIN_PASSWORD = "admin123"


def ensure_default_admin():
    """Make sure admin@gmail.com / admin123 always exists and is an admin."""
    admin = User.query.filter_by(email=DEFAULT_ADMIN_EMAIL).first()
    if admin is None:
        admin = User(
            name=DEFAULT_ADMIN_NAME,
            email=DEFAULT_ADMIN_EMAIL,
            phone="03000000000",
        )
        db.session.add(admin)
    admin.role = "admin"
    admin.password_hash = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
    db.session.commit()


with app.app_context():
    db.create_all()      # also creates the new waiting_entry table
    ensure_schema()
    ensure_default_admin()


# ---------------- VALIDATION HELPERS ----------------

EMAIL_RE = re.compile(r"^[A-Za-z0-9._+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?\d{10,13}$")
MIN_PASSWORD_LENGTH = 6


def clean_phone(raw):
    """Spaces aur dashes hata deta hai: '0300-123 4567' -> '03001234567'."""
    return re.sub(r"[\s\-]", "", raw or "")


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def check_priority(new_priority, current=None):
    """Returns (priority, error). Emergency and VIP can only be given by an admin."""
    new_priority = (new_priority or "Normal").strip()
    if new_priority not in PRIORITY_LEVELS:
        return None, "Invalid priority."
    if (
        new_priority != current
        and new_priority in ADMIN_ONLY_PRIORITIES
        and current_user.role != "admin"
    ):
        return None, f"Only an admin can set the {new_priority} priority."
    return new_priority, None


def run_waiting_assignment():
    """A slot just became free: serve the waiting list (priority order)."""
    for vehicle, slot in assign_waiting_vehicles():
        flash(
            f"Waiting list: {vehicle.vehicle_number} ({vehicle.priority}) "
            f"was parked at slot {slot.slot_number}.",
            "info",
        )


@app.route("/")
def home():
    return render_template("home.html")


# ---------------- AUTH ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()
        password = request.form["password"]

        if not name or not email or not phone or not password:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("register"))

        if not EMAIL_RE.match(email):
            flash("Please enter a valid email address (like name@example.com).", "danger")
            return redirect(url_for("register"))

        phone = clean_phone(phone)
        if not PHONE_RE.match(phone):
            flash("Phone must contain digits only (10 to 13 digits, optional + at the start).", "danger")
            return redirect(url_for("register"))

        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("This email is already registered.", "danger")
            return redirect(url_for("register"))

        user = User(
            name=name,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not EMAIL_RE.match(email):
            flash("Please enter a valid email address.", "danger")
            return redirect(url_for("login"))

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
@login_required
def dashboard():
    vehicle_count = Vehicle.query.filter_by(user_id=current_user.id).count()
    available_slots = ParkingSlot.query.filter_by(status="available").count()
    waiting_count = WaitingEntry.query.filter_by(status="waiting").count()
    return render_template(
        "dashboard.html",
        vehicle_count=vehicle_count,
        available_slots=available_slots,
        waiting_count=waiting_count,
    )


# ---------------- PROFILE ----------------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()

        if not name or not email:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("profile"))

        if not EMAIL_RE.match(email):
            flash("Please enter a valid email address (like name@example.com).", "danger")
            return redirect(url_for("profile"))

        phone = clean_phone(phone)
        if phone and not PHONE_RE.match(phone):
            flash("Phone must contain digits only (10 to 13 digits, optional + at the start).", "danger")
            return redirect(url_for("profile"))

        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != current_user.id:
            flash("This email is already used by another account.", "danger")
            return redirect(url_for("profile"))

        current_user.name = name
        current_user.email = email
        current_user.phone = phone
        db.session.commit()

        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))

    # Payment history: sirf apni gaadiyon ki payments, naye exit pehle
    history_query = (
        Payment.query.join(ParkingRecord, Payment.record_id == ParkingRecord.id)
        .join(Vehicle, ParkingRecord.vehicle_id == Vehicle.id)
        .filter(Vehicle.user_id == current_user.id)
        .order_by(ParkingRecord.exit_time.desc())
    )
    history = []
    total_paid = 0
    total_pending = 0
    for pay in history_query.all():
        record = db.session.get(ParkingRecord, pay.record_id)
        history.append(
            {
                "payment": pay,
                "record": record,
                "vehicle": db.session.get(Vehicle, record.vehicle_id),
                "slot": db.session.get(ParkingSlot, record.slot_id),
                "hours": calculate_fee(record.entry_time, record.exit_time)[0],
            }
        )
        if pay.status == "paid":
            total_paid += pay.amount
        else:
            total_pending += pay.amount

    return render_template(
        "profile.html",
        history=history,
        total_paid=total_paid,
        total_pending=total_pending,
    )


# ---------------- VEHICLES ----------------

@app.route("/vehicles")
@login_required
def vehicles():
    my_vehicles = Vehicle.query.filter_by(user_id=current_user.id).all()
    return render_template("vehicles.html", vehicles=my_vehicles)


@app.route("/vehicles/add", methods=["GET", "POST"])
@login_required
def add_vehicle():
    if request.method == "POST":
        number = request.form["vehicle_number"].strip().upper()
        vtype = request.form["vehicle_type"].strip()
        priority, error = check_priority(request.form.get("priority"))

        if not number or not vtype:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("add_vehicle"))

        if error:
            flash(error, "danger")
            return redirect(url_for("add_vehicle"))

        if Vehicle.query.filter_by(vehicle_number=number).first():
            flash("This vehicle number is already registered.", "danger")
            return redirect(url_for("add_vehicle"))

        vehicle = Vehicle(
            vehicle_number=number,
            vehicle_type=vtype,
            priority=priority,
            user_id=current_user.id,
        )
        db.session.add(vehicle)
        db.session.commit()

        flash("Vehicle added successfully!", "success")
        return redirect(url_for("vehicles"))

    return render_template(
        "vehicle_form.html", vehicle=None, priorities=PRIORITY_LEVELS
    )


@app.route("/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
@login_required
def edit_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.user_id != current_user.id:
        abort(404)

    if request.method == "POST":
        number = request.form["vehicle_number"].strip().upper()
        vtype = request.form["vehicle_type"].strip()
        priority, error = check_priority(
            request.form.get("priority"), current=vehicle.priority
        )

        if not number or not vtype:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("edit_vehicle", vehicle_id=vehicle_id))

        if error:
            flash(error, "danger")
            return redirect(url_for("edit_vehicle", vehicle_id=vehicle_id))

        existing = Vehicle.query.filter_by(vehicle_number=number).first()
        if existing and existing.id != vehicle.id:
            flash("This vehicle number is already registered.", "danger")
            return redirect(url_for("edit_vehicle", vehicle_id=vehicle_id))

        vehicle.vehicle_number = number
        vehicle.vehicle_type = vtype
        vehicle.priority = priority
        db.session.commit()

        flash("Vehicle updated successfully!", "success")
        return redirect(url_for("vehicles"))

    return render_template(
        "vehicle_form.html", vehicle=vehicle, priorities=PRIORITY_LEVELS
    )


@app.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
@login_required
def delete_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.user_id != current_user.id:
        abort(404)

    # Member 4: parked vehicle delete nahi hoga (record toot jayega)
    still_parked = ParkingRecord.query.filter(
        ParkingRecord.vehicle_id == vehicle.id,
        ParkingRecord.exit_time.is_(None),
    ).first()
    if still_parked:
        flash("This vehicle is currently parked. Exit it first.", "danger")
        return redirect(url_for("vehicles"))

    # Payment pending hai to bhi delete nahi hogi (receipt toot jayegi)
    if vehicle.id in waiting_vehicle_ids():
        flash("This vehicle is in the waiting list. Leave the queue first.", "danger")
        return redirect(url_for("vehicles"))

    unpaid = (
        Payment.query.filter_by(status="pending")
        .join(ParkingRecord, Payment.record_id == ParkingRecord.id)
        .filter(ParkingRecord.vehicle_id == vehicle.id)
        .first()
    )
    if unpaid:
        flash("This vehicle has a pending payment. Pay it first.", "danger")
        return redirect(url_for("vehicles"))

    db.session.delete(vehicle)
    db.session.commit()

    flash("Vehicle deleted.", "success")
    return redirect(url_for("vehicles"))


# ---------------- PARKING SLOTS (Member 3) ----------------

@app.route("/slots")
@login_required
def slots():
    all_slots = ParkingSlot.query.order_by(ParkingSlot.slot_number).all()
    return render_template("slots.html", slots=all_slots)

@app.route("/slots/add", methods=["GET", "POST"])
@admin_required
def add_slot():
    if request.method == "POST":
        number = request.form["slot_number"].strip().upper()
        stype = request.form["slot_type"].strip()
        distance = request.form["distance"].strip()

        if not number or not stype or not distance:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("add_slot"))

        try:
            distance = float(distance)
        except ValueError:
            flash("Distance must be a number.", "danger")
            return redirect(url_for("add_slot"))

        if distance < 0:
            flash("Distance cannot be negative.", "danger")
            return redirect(url_for("add_slot"))

        if ParkingSlot.query.filter_by(slot_number=number).first():
            flash("This slot number already exists.", "danger")
            return redirect(url_for("add_slot"))

        slot = ParkingSlot(
            slot_number=number,
            slot_type=stype,
            distance=distance,
            status="available",
        )
        db.session.add(slot)
        db.session.commit()

        flash("Slot added successfully!", "success")
        run_waiting_assignment()
        return redirect(url_for("slots"))

    return render_template("slot_form.html", slot=None, slot_types=SLOT_TYPES)

@app.route("/slots/<int:slot_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_slot(slot_id):
    slot = db.session.get(ParkingSlot, slot_id)
    if slot is None:
        abort(404)

    if request.method == "POST":
        number = request.form["slot_number"].strip().upper()
        stype = request.form["slot_type"].strip()
        distance = request.form["distance"].strip()

        if not number or not stype or not distance:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("edit_slot", slot_id=slot_id))

        try:
            distance = float(distance)
        except ValueError:
            flash("Distance must be a number.", "danger")
            return redirect(url_for("edit_slot", slot_id=slot_id))

        if distance < 0:
            flash("Distance cannot be negative.", "danger")
            return redirect(url_for("edit_slot", slot_id=slot_id))

        existing = ParkingSlot.query.filter_by(slot_number=number).first()
        if existing and existing.id != slot.id:
            flash("This slot number already exists.", "danger")
            return redirect(url_for("edit_slot", slot_id=slot_id))

        slot.slot_number = number
        slot.slot_type = stype
        slot.distance = distance
        db.session.commit()

        flash("Slot updated successfully!", "success")
        run_waiting_assignment()
        return redirect(url_for("slots"))

    return render_template("slot_form.html", slot=slot, slot_types=SLOT_TYPES)


@app.route("/slots/<int:slot_id>/delete", methods=["POST"])
@admin_required
def delete_slot(slot_id):
    slot = db.session.get(ParkingSlot, slot_id)
    if slot is None:
        abort(404)

    if slot.status in ("occupied", "reserved"):
        flash("Occupied or reserved slot cannot be deleted.", "danger")
        return redirect(url_for("slots"))

    db.session.delete(slot)
    db.session.commit()

    flash("Slot deleted.", "success")
    return redirect(url_for("slots"))


VALID_SLOT_STATUSES = ["available", "occupied", "reserved", "maintenance"]


@app.route("/slots/<int:slot_id>/status", methods=["POST"])
@admin_required
def update_slot_status(slot_id):
    slot = db.session.get(ParkingSlot, slot_id)
    if slot is None:
        abort(404)

    new_status = request.form.get("status", "").strip().lower()

    if new_status not in VALID_SLOT_STATUSES:
        flash("Invalid status.", "danger")
        return redirect(url_for("slots"))

    slot.status = new_status
    db.session.commit()

    flash(f"Slot {slot.slot_number} is now {new_status}.", "success")
    if new_status == "available":
        run_waiting_assignment()
    return redirect(url_for("slots"))


# ---------------- ENTRY / EXIT / FEE (Member 4) ----------------

FIRST_HOUR_FEE = 50       # pehla ghanta
SECOND_HOUR_FEE = 80      # doosra ghanta
HOURLY_INCREASE = 0.20    # uske baad har ghante ka rate pichle se 20% zyada


def calculate_fee(entry_time, exit_time):
    """Escalating fee. Partial hour = poora ghanta.
    Rates: 50, 80, 96, 115.2, 138.24 ... (har ghanta pichle se 20% zyada)."""
    seconds = (exit_time - entry_time).total_seconds()
    hours = max(1, math.ceil(seconds / 3600))

    fee = FIRST_HOUR_FEE
    rate = SECOND_HOUR_FEE
    for _ in range(1, hours):
        fee += rate
        rate *= 1 + HOURLY_INCREASE

    # Rs.10 ke multiple tak upar round (226 -> 230). round(.., 2) float error se bachata hai.
    fee = math.ceil(round(fee, 2) / 10) * 10

    return hours, fee


def active_records_for_current_user():
    """Jo gaadiyan abhi parked hain (exit_time None). Admin ko sab, user ko sirf apni."""
    query = ParkingRecord.query.filter(ParkingRecord.exit_time.is_(None))
    if current_user.role != "admin":
        query = query.join(
            Vehicle, ParkingRecord.vehicle_id == Vehicle.id
        ).filter(Vehicle.user_id == current_user.id)
    return query.order_by(ParkingRecord.entry_time).all()


@app.route("/entry", methods=["GET", "POST"])
@login_required
def vehicle_entry():
    vehicle_query = Vehicle.query
    if current_user.role != "admin":
        vehicle_query = vehicle_query.filter_by(user_id=current_user.id)

    parked_ids = {
        r.vehicle_id
        for r in ParkingRecord.query.filter(ParkingRecord.exit_time.is_(None)).all()
    }
    waiting_ids = waiting_vehicle_ids()

    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id", type=int)
        vehicle = vehicle_query.filter_by(id=vehicle_id).first() if vehicle_id else None

        if vehicle is None:
            flash("Please select a valid vehicle.", "danger")
            return redirect(url_for("vehicle_entry"))

        if vehicle.id in parked_ids:
            flash("This vehicle is already parked.", "danger")
            return redirect(url_for("vehicle_entry"))

        if vehicle.id in waiting_ids:
            flash("This vehicle is already in the waiting list.", "danger")
            return redirect(url_for("vehicle_entry"))

        # User khud slot chunta hai. Server pe dobara check: slot abhi bhi available hai?
        slot_id = request.form.get("slot_id", type=int)
        slot = db.session.get(ParkingSlot, slot_id) if slot_id else None

        if slot is None:
            flash("Please select a parking slot.", "danger")
            return redirect(url_for("vehicle_entry"))

        if slot.status != "available":
            flash(
                f"Slot {slot.slot_number} is not available ({slot.status}). Choose another slot.",
                "danger",
            )
            return redirect(url_for("vehicle_entry"))

        record = ParkingRecord(
            vehicle_id=vehicle.id,
            slot_id=slot.id,
            entry_time=datetime.now(),
        )
        slot.status = "occupied"
        db.session.add(record)
        db.session.commit()

        flash(
            f"{vehicle.vehicle_number} parked at slot {slot.slot_number}.",
            "success",
        )
        return redirect(url_for("vehicle_exit"))

    free_vehicles = [
        v for v in vehicle_query.all()
        if v.id not in parked_ids and v.id not in waiting_ids
    ]
    all_slots = ParkingSlot.query.order_by(ParkingSlot.slot_number).all()
    available_count = sum(1 for s in all_slots if s.status == "available")
    return render_template(
        "entry.html",
        vehicles=free_vehicles,
        slots=all_slots,
        available_count=available_count,
    )


@app.route("/entry/smart", methods=["POST"])
@login_required
def smart_entry():
    """Phase 6: the system picks the slot (type -> priority -> min heap)."""
    vehicle_query = Vehicle.query
    if current_user.role != "admin":
        vehicle_query = vehicle_query.filter_by(user_id=current_user.id)

    vehicle_id = request.form.get("vehicle_id", type=int)
    vehicle = vehicle_query.filter_by(id=vehicle_id).first() if vehicle_id else None
    if vehicle is None:
        flash("Please select a valid vehicle.", "danger")
        return redirect(url_for("vehicle_entry"))

    already_parked = ParkingRecord.query.filter(
        ParkingRecord.vehicle_id == vehicle.id,
        ParkingRecord.exit_time.is_(None),
    ).first()
    if already_parked:
        flash("This vehicle is already parked.", "danger")
        return redirect(url_for("vehicle_entry"))

    if vehicle.id in waiting_vehicle_ids():
        flash("This vehicle is already in the waiting list.", "danger")
        return redirect(url_for("waiting"))

    result = smart_park(vehicle)
    steps = " > ".join(result["trace"][1:])

    if result["status"] == "parked":
        slot = result["slot"]
        flash(
            f"{vehicle.vehicle_number} parked at slot {slot.slot_number} "
            f"({slot.distance:g} m from the gate).",
            "success",
        )
        flash(f"Smart allocation: {steps}", "info")
        return redirect(url_for("vehicle_exit"))

    flash(
        f"Parking is full for {vehicle.vehicle_number}. "
        f"Added to the waiting list at position {result['position']}.",
        "warning",
    )
    return redirect(url_for("waiting"))


@app.route("/exit")
@login_required
def vehicle_exit():
    now = datetime.now()
    rows = []
    for record in active_records_for_current_user():
        hours, fee = calculate_fee(record.entry_time, now)
        rows.append(
            {
                "record": record,
                "vehicle": db.session.get(Vehicle, record.vehicle_id),
                "slot": db.session.get(ParkingSlot, record.slot_id),
                "hours": hours,
                "fee": fee,
            }
        )
    return render_template(
        "exit.html",
        rows=rows,
        pending=pending_payment_rows(),
    )


@app.route("/exit/<int:record_id>/checkout", methods=["POST"])
@login_required
def checkout(record_id):
    record = db.session.get(ParkingRecord, record_id)
    if record is None or record.exit_time is not None:
        abort(404)

    vehicle = db.session.get(Vehicle, record.vehicle_id)
    if vehicle is None or (
        current_user.role != "admin" and vehicle.user_id != current_user.id
    ):
        abort(404)

    now = datetime.now()
    hours, fee = calculate_fee(record.entry_time, now)

    record.exit_time = now
    record.fee = fee

    slot = db.session.get(ParkingSlot, record.slot_id)
    if slot is not None and slot.status == "occupied":
        slot.status = "available"

    db.session.add(Payment(record_id=record.id, amount=fee, status="pending"))
    db.session.commit()

    flash(
        f"{vehicle.vehicle_number} exited. {hours} hour(s), fee: Rs.{fee:.0f}. Please complete the payment.",
        "success",
    )
    run_waiting_assignment()       # the freed slot goes to the next waiting vehicle
    return redirect(url_for("payment", record_id=record.id))


# ---------------- PAYMENT (Member 4, demo page) ----------------

# Sirf dikhane ke liye, database mein save nahi hota.
PAYMENT_METHODS = ["Cash", "Card", "JazzCash", "Easypaisa"]


def pending_payment_rows():
    """Wo payments jo abhi pending hain. Admin ko sab, user ko sirf apni."""
    query = (
        Payment.query.filter_by(status="pending")
        .join(ParkingRecord, Payment.record_id == ParkingRecord.id)
        .join(Vehicle, ParkingRecord.vehicle_id == Vehicle.id)
    )
    if current_user.role != "admin":
        query = query.filter(Vehicle.user_id == current_user.id)

    rows = []
    for pay in query.order_by(Payment.id).all():
        record = db.session.get(ParkingRecord, pay.record_id)
        rows.append(
            {
                "payment": pay,
                "record": record,
                "vehicle": db.session.get(Vehicle, record.vehicle_id),
                "slot": db.session.get(ParkingSlot, record.slot_id),
            }
        )
    return rows


@app.route("/payment/<int:record_id>", methods=["GET", "POST"])
@login_required
def payment(record_id):
    record = db.session.get(ParkingRecord, record_id)
    if record is None or record.exit_time is None:
        abort(404)

    vehicle = db.session.get(Vehicle, record.vehicle_id)
    if vehicle is None or (
        current_user.role != "admin" and vehicle.user_id != current_user.id
    ):
        abort(404)

    pay = Payment.query.filter_by(record_id=record.id).first()
    if pay is None:
        abort(404)

    if request.method == "POST":
        if pay.status == "paid":
            flash("This payment is already completed.", "info")
        else:
            method = request.form.get("method", "")
            if method not in PAYMENT_METHODS:
                flash("Please select a payment method.", "danger")
                return redirect(url_for("payment", record_id=record.id))

            pay.status = "paid"
            db.session.commit()
            flash(
                f"Payment of Rs.{pay.amount:.0f} received via {method} (demo).",
                "success",
            )
        return redirect(url_for("payment", record_id=record.id))

    slot = db.session.get(ParkingSlot, record.slot_id)
    hours, _ = calculate_fee(record.entry_time, record.exit_time)
    return render_template(
        "payment.html",
        record=record,
        vehicle=vehicle,
        slot=slot,
        payment=pay,
        hours=hours,
        methods=PAYMENT_METHODS,
    )


# ---------------- WAITING LIST (Phase 6: Queue + Priority Queue) ----------------

@app.route("/waiting")
@login_required
def waiting():
    rows = []
    total = 0
    for position, (rank, entry) in enumerate(build_waiting_pq().ordered(), start=1):
        total += 1
        vehicle = db.session.get(Vehicle, entry.vehicle_id)
        if current_user.role != "admin" and vehicle.user_id != current_user.id:
            continue                      # users only see their own rows
        rows.append({"position": position, "entry": entry, "vehicle": vehicle})
    return render_template("waiting.html", rows=rows, total=total)


@app.route("/waiting/<int:entry_id>/cancel", methods=["POST"])
@login_required
def cancel_waiting_entry(entry_id):
    entry = db.session.get(WaitingEntry, entry_id)
    if entry is None or entry.status != "waiting":
        abort(404)
    vehicle = db.session.get(Vehicle, entry.vehicle_id)
    if current_user.role != "admin" and vehicle.user_id != current_user.id:
        abort(404)
    cancel_waiting(entry)
    flash(f"{vehicle.vehicle_number} left the waiting list.", "success")
    return redirect(url_for("waiting"))


@app.route("/waiting/process", methods=["POST"])
@admin_required
def process_waiting():
    before = WaitingEntry.query.filter_by(status="waiting").count()
    run_waiting_assignment()
    after = WaitingEntry.query.filter_by(status="waiting").count()
    if before == after:
        flash("No waiting vehicle could be served right now.", "warning")
    return redirect(url_for("waiting"))


# ---------------- SEARCH (Phase 5: Hash Table) ----------------

@app.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    kind = request.args.get("type", "vehicle")
    is_admin = current_user.role == "admin"

    if kind not in ("vehicle", "slot", "user"):
        kind = "vehicle"
    if kind == "user" and not is_admin:
        abort(403)

    results, info = [], None

    if q and kind == "vehicle":
        hits, info = search_index.search_vehicle(q)
        for hit in hits:
            vehicle = db.session.get(Vehicle, hit["vehicle_id"])
            if vehicle is None:
                continue
            if not is_admin and vehicle.user_id != current_user.id:
                continue                  # do not reveal other people's vehicles
            record = db.session.get(ParkingRecord, hit["record_id"]) if hit["record_id"] else None
            results.append({
                "vehicle": vehicle,
                "owner": db.session.get(User, vehicle.user_id),
                "slot": db.session.get(ParkingSlot, hit["slot_id"]) if hit["slot_id"] else None,
                "record": record,
                "waiting": vehicle.id in waiting_vehicle_ids(),
            })

    elif q and kind == "slot":
        slot_ids, info = search_index.search_slot(q)
        for slot_id in slot_ids:
            slot = db.session.get(ParkingSlot, slot_id)
            if slot is None:
                continue
            record = ParkingRecord.query.filter(
                ParkingRecord.slot_id == slot.id,
                ParkingRecord.exit_time.is_(None),
            ).first()
            vehicle = db.session.get(Vehicle, record.vehicle_id) if record else None
            can_see = vehicle is not None and (is_admin or vehicle.user_id == current_user.id)
            results.append({
                "slot": slot,
                "record": record,
                "vehicle": vehicle if can_see else None,
            })

    elif q and kind == "user":
        user_ids, info = search_index.search_user(q)
        for user_id in user_ids:
            user = db.session.get(User, user_id)
            if user is None:
                continue
            cars = []
            for v in Vehicle.query.filter_by(user_id=user.id).all():
                rec = ParkingRecord.query.filter(
                    ParkingRecord.vehicle_id == v.id,
                    ParkingRecord.exit_time.is_(None),
                ).first()
                cars.append({
                    "vehicle": v,
                    "slot": db.session.get(ParkingSlot, rec.slot_id) if rec else None,
                })
            results.append({"user": user, "vehicles": cars})

    return render_template("search.html", q=q, kind=kind, results=results, info=info)


# ---------------- DSA LAB (Phase 5 + 6 visualiser, admin) ----------------

@app.route("/dsa-lab")
@admin_required
def dsa_lab():
    search_index.ensure_fresh()
    hash_stats = [
        ("Vehicles (plate -> parking info)", search_index.vehicles.stats()),
        ("Slots (slot number -> slot)", search_index.slots.stats()),
        ("Users (email -> user)", search_index.emails.stats()),
    ]
    buckets = search_index.vehicles.bucket_view(10)

    heap_views = []
    for slot_type, heap in sorted(build_slot_heaps().items()):
        levels = [
            [f"{key[1]} ({key[0]:g} m)" for key, _ in level]
            for level in heap.levels()
        ]
        top_key, _ = heap.peek()
        heap_views.append({
            "type": slot_type,
            "size": len(heap),
            "next": f"{top_key[1]} ({top_key[0]:g} m)",
            "levels": levels,
        })

    def describe(entry):
        vehicle = db.session.get(Vehicle, entry.vehicle_id)
        return {"number": vehicle.vehicle_number, "priority": vehicle.priority or "Normal"}

    fifo = [describe(e) for e in build_waiting_fifo()]
    priority_order = [describe(e) for _, e in build_waiting_pq().ordered()]

    return render_template(
        "dsa_lab.html",
        hash_stats=hash_stats,
        buckets=buckets,
        rebuilds=search_index.rebuilds,
        heap_views=heap_views,
        fifo=fifo,
        priority_order=priority_order,
        preference=SLOT_PREFERENCE,
    )


# ---------------- ADMIN ----------------

@app.route("/admin/users")
@admin_required
def admin_users():
    users = User.query.order_by(User.id).all()
    return render_template("admin_users.html", users=users)


@app.route("/admin/vehicles")
@admin_required
def admin_vehicles():
    rows = []
    for v in Vehicle.query.order_by(Vehicle.id).all():
        rows.append({"vehicle": v, "owner": db.session.get(User, v.user_id)})
    return render_template("admin_vehicles.html", rows=rows, priorities=PRIORITY_LEVELS)


@app.route("/admin/vehicles/<int:vehicle_id>/priority", methods=["POST"])
@admin_required
def set_vehicle_priority(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if vehicle is None:
        abort(404)
    priority = request.form.get("priority", "")
    if priority not in PRIORITY_LEVELS:
        flash("Invalid priority.", "danger")
        return redirect(url_for("admin_vehicles"))
    vehicle.priority = priority
    db.session.commit()
    flash(f"{vehicle.vehicle_number} is now {priority}.", "success")
    return redirect(url_for("admin_vehicles"))


if __name__ == "__main__":
    app.run(debug=True)