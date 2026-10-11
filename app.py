
import os

from flask import Flask, render_template
from models import db
import models


app = Flask(__name__)

os.makedirs(app.instance_path, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///parking.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


with app.app_context():
    db.create_all()


@app.route("/")
def home():
    return render_template("home.html")


if __name__ == "__main__":
    app.run(debug=True)
