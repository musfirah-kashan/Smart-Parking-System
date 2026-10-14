import sys

from app import app
from models import db, User

with app.app_context():
    if len(sys.argv) < 2:
        print("Registered users:")
        for u in User.query.all():
            print("-", u.email, "| role:", u.role)
        sys.exit()

    email = sys.argv[1].strip().lower()
    user = User.query.filter_by(email=email).first()

    if user is None:
        print("User not found. Registered emails are:")
        for u in User.query.all():
            print("-", u.email)
    else:
        user.role = "admin"
        db.session.commit()
        print(user.email, "is now admin")