from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(20), default="user")


class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_number = db.Column(
        db.String(20), unique=True, nullable=False
    )
    vehicle_type = db.Column(db.String(30), nullable=False)
    # Phase 6: Emergency / Disabled / EV / VIP / Normal
    priority = db.Column(db.String(20), default="Normal")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))


class ParkingSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slot_number = db.Column(db.String(20), unique=True, nullable=False)
    slot_type = db.Column(db.String(30), default="normal")
    status = db.Column(db.String(20), default="available")
    distance = db.Column(db.Float, default=0.0)


class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    slot_id = db.Column(
        db.Integer, db.ForeignKey("parking_slot.id")
    )
    status = db.Column(db.String(20), default="pending")


class ParkingRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(
        db.Integer, db.ForeignKey("vehicle.id")
    )
    slot_id = db.Column(
        db.Integer, db.ForeignKey("parking_slot.id")
    )
    entry_time = db.Column(db.DateTime)
    exit_time = db.Column(db.DateTime)
    fee = db.Column(db.Float, default=0.0)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(
        db.Integer, db.ForeignKey("parking_record.id")
    )
    amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default="pending")


class WaitingEntry(db.Model):
    """A vehicle standing in the waiting list because parking was full (Phase 6)."""
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"))
    # waiting -> assigned (got a slot) or cancelled (left the queue)
    status = db.Column(db.String(20), default="waiting")
    joined_at = db.Column(db.DateTime)
    assigned_at = db.Column(db.DateTime)