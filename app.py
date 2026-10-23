import os
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, Vehicle, ParkingSlot
import models


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


with app.app_context():
    db.create_all()


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


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
    return render_template(
        "dashboard.html",
        vehicle_count=vehicle_count,
        available_slots=available_slots,
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

    return render_template("profile.html")


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

        if not number or not vtype:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("add_vehicle"))

        if Vehicle.query.filter_by(vehicle_number=number).first():
            flash("This vehicle number is already registered.", "danger")
            return redirect(url_for("add_vehicle"))

        vehicle = Vehicle(
            vehicle_number=number,
            vehicle_type=vtype,
            user_id=current_user.id,
        )
        db.session.add(vehicle)
        db.session.commit()

        flash("Vehicle added successfully!", "success")
        return redirect(url_for("vehicles"))

    return render_template("vehicle_form.html", vehicle=None)


@app.route("/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
@login_required
def edit_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.user_id != current_user.id:
        abort(404)

    if request.method == "POST":
        number = request.form["vehicle_number"].strip().upper()
        vtype = request.form["vehicle_type"].strip()

        if not number or not vtype:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("edit_vehicle", vehicle_id=vehicle_id))

        existing = Vehicle.query.filter_by(vehicle_number=number).first()
        if existing and existing.id != vehicle.id:
            flash("This vehicle number is already registered.", "danger")
            return redirect(url_for("edit_vehicle", vehicle_id=vehicle_id))

        vehicle.vehicle_number = number
        vehicle.vehicle_type = vtype
        db.session.commit()

        flash("Vehicle updated successfully!", "success")
        return redirect(url_for("vehicles"))

    return render_template("vehicle_form.html", vehicle=vehicle)


@app.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
@login_required
def delete_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.user_id != current_user.id:
        abort(404)

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
        return redirect(url_for("slots"))

    return render_template("slot_form.html", slot=None)

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
        return redirect(url_for("slots"))

    return render_template("slot_form.html", slot=slot)


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
    return redirect(url_for("slots"))


# ---------------- ADMIN ----------------

@app.route("/admin/users")
@admin_required
def admin_users():
    users = User.query.order_by(User.id).all()
    return render_template("admin_users.html", users=users)


if __name__ == "__main__":
    app.run(debug=True)