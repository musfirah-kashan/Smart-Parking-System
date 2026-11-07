"""Sample data seeder for Smart Parking System.

Usage (project root mein, venv active karke):
    python seed_sample_data.py            # data add karta hai (duplicate skip)
    python seed_sample_data.py --history  # + purani completed parking/payments (reports/analytics ke liye)

Safe hai: jo cheez pehle se hai (email, plate, slot number) dobara add nahi hoti.
Test users ka password sab ka: test1234
Admin: admin@gmail.com / admin123
"""
import sys
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import app, calculate_fee
from models import db, User, Vehicle, ParkingSlot, ParkingRecord, Payment
from dsa.parking_engine import normalize_plate

PASSWORD = "test1234"

USERS = [
    ("Ayesha Khan",  "ayesha@test.com",  "03001234567"),
    ("Bilal Ahmed",  "bilal@test.com",   "0312-7654321"),
    ("Sara Malik",   "sara@test.com",    "+923331112233"),
    ("Hamza Ali",    "hamza@test.com",   "03451239876"),
]

# (slot_number, slot_type, distance_in_metres)
SLOTS = [
    ("A1", "normal", 10), ("A2", "normal", 15), ("A3", "normal", 20),
    ("A4", "normal", 30), ("A5", "normal", 45),
    ("B1", "bike", 8),   ("B2", "bike", 12),
    ("H1", "handicapped", 5),
    ("E1", "ev", 18),    ("E2", "ev", 25),
    ("V1", "vip", 6),
    ("X1", "emergency", 3),
]

# (owner_email, plate, type, priority)
VEHICLES = [
    ("ayesha@test.com", "LEA-1234",  "Car",   "Normal"),
    ("ayesha@test.com", "KHI-5678",  "Bike",  "Normal"),
    ("bilal@test.com",  "ABC-123",   "Car",   "EV"),
    ("bilal@test.com",  "BKL-7788",  "Van",   "Normal"),
    ("sara@test.com",   "RWP-4321",  "Car",   "Disabled"),
    ("sara@test.com",   "AMB-911",   "Van",   "Emergency"),
    ("hamza@test.com",  "VIP-007",   "Car",   "VIP"),
    ("hamza@test.com",  "TRK-9090",  "Truck", "Normal"),
    ("hamza@test.com",  "KHI-1111",  "Car",   "Normal"),
    ("hamza@test.com",  "KHI-2222",  "Car",   "Normal"),
    ("hamza@test.com",  "KHI-3333",  "Car",   "Normal"),
    ("hamza@test.com",  "KHI-4444",  "Car",   "Normal"),
]

# (plate, slot_number, hours_ago_entered, hours_parked) -> completed history
HISTORY = [
    ("LEA-1234", "A1", 48, 2),
    ("KHI-5678", "B1", 30, 1),
    ("ABC-123",  "E1", 26, 3),
    ("VIP-007",  "V1", 24, 5),
    ("KHI-1111", "A2", 10, 1),
    ("RWP-4321", "H1", 5, 4),
]


def seed(with_history=False):
    added = {"users": 0, "slots": 0, "vehicles": 0, "history": 0}

    for name, email, phone in USERS:
        if User.query.filter_by(email=email).first():
            continue
        db.session.add(User(
            name=name, email=email, phone=phone.replace("-", ""),
            password_hash=generate_password_hash(PASSWORD), role="user",
        ))
        added["users"] += 1
    db.session.commit()

    for number, stype, dist in SLOTS:
        if ParkingSlot.query.filter_by(slot_number=number).first():
            continue
        db.session.add(ParkingSlot(slot_number=number, slot_type=stype,
                                   distance=float(dist), status="available"))
        added["slots"] += 1
    db.session.commit()

    existing = {normalize_plate(v.vehicle_number) for v in Vehicle.query.all()}
    for email, plate, vtype, priority in VEHICLES:
        if normalize_plate(plate) in existing:
            continue
        owner = User.query.filter_by(email=email).first()
        db.session.add(Vehicle(vehicle_number=plate, vehicle_type=vtype,
                               priority=priority, user_id=owner.id))
        added["vehicles"] += 1
    db.session.commit()

    if with_history:
        now = datetime.now()
        for plate, slot_no, ago, hrs in HISTORY:
            v = next((x for x in Vehicle.query.all()
                      if normalize_plate(x.vehicle_number) == normalize_plate(plate)), None)
            s = ParkingSlot.query.filter_by(slot_number=slot_no).first()
            if v is None or s is None:
                continue
            entry = now - timedelta(hours=ago)
            exit_ = entry + timedelta(hours=hrs)
            _, fee = calculate_fee(entry, exit_)
            rec = ParkingRecord(vehicle_id=v.id, slot_id=s.id,
                                entry_time=entry, exit_time=exit_, fee=fee)
            db.session.add(rec)
            db.session.flush()
            db.session.add(Payment(record_id=rec.id, amount=fee, status="paid",
                                   paid_at=exit_, method="Cash"))
            added["history"] += 1
        db.session.commit()

    return added


if __name__ == "__main__":
    with app.app_context():
        result = seed(with_history="--history" in sys.argv)
    print("Seed done:", result)
    print(f"Test users password: {PASSWORD}  |  Admin: admin@gmail.com / admin123")
