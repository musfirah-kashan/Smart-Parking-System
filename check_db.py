
from app import app
from models import db

with app.app_context():
    print("Database tables:")

    for table_name in db.metadata.tables:
        print(table_name)

    print("\nDatabase connection successful!")
