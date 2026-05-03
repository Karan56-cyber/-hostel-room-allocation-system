from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
    Response,
)
import json

app = Flask(__name__)
app.secret_key = "simple-secret"

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data_store.json"

ROOM_TYPES = ["Single AC", "Single Non-AC", "Double AC", "Double Non-AC"]
YEAR_GROUPS = ["Freshman", "Senior"]
GENDERS = ["Male", "Female"]


def default_data() -> dict[str, Any]:
    return {"students": [], "rooms": [], "waiting": []}


def read_data() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return default_data()
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def write_data(data: dict[str, Any]) -> None:
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_logged_in() -> bool:
    return session.get("warden_auth") is True


def sort_students(students: list[dict[str, Any]]):
    return sorted(students, key=lambda s: (-s["year"], s.get("cgpa", 0)))


def execute_allocation(data: dict[str, Any]):
    for room in data["rooms"]:
        room["occupied"] = 0
        room["residents"] = []
        room["gender"] = None

    data["waiting"] = []

    for student in sort_students(data["students"]):
        assigned = False
        group = "Freshman" if student["year"] == 1 else "Senior"

        for pref in student["prefs"]:
            for room in data["rooms"]:
                if room["type"] != pref:
                    continue
                if room["yearGroup"] != group:
                    continue
                if room["occupied"] >= room["capacity"]:
                    continue
                if room["gender"] not in (None, student["gender"]):
                    continue

                room["occupied"] += 1
                room["gender"] = student["gender"]
                room["residents"].append(student["name"])
                assigned = True
                break

            if assigned:
                break

        if not assigned:
            data["waiting"].append(student)


def build_stats(data):
    total = len(data["students"])
    allocated = total - len(data["waiting"])
    return {
        "students": total,
        "rooms": len(data["rooms"]),
        "allocated": allocated,
        "waiting": len(data["waiting"]),
    }


@app.route("/")
def index():
    if not is_logged_in():
        return render_template("index.html", login_only=True)

    data = read_data()
    stats = build_stats(data)
    section = request.args.get("section", "dashboard")

    return render_template(
        "index.html",
        login_only=False,
        data=data,
        stats=stats,
        room_types=ROOM_TYPES,
        year_groups=YEAR_GROUPS,
        genders=GENDERS,
        active_section=section,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("warden_id") == "admin" and request.form.get("password") == "warden123":
            session["warden_auth"] = True
            return redirect(url_for("index"))
        flash("Invalid login")
    return render_template("index.html", login_only=True)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/students", methods=["POST"])
def add_student():
    if not is_logged_in():
        return redirect(url_for("login"))

    data = read_data()

    student = {
        "id": request.form.get("id"),
        "name": request.form.get("name"),
        "year": int(request.form.get("year", 1)),
        "gender": request.form.get("gender"),
        "cgpa": float(request.form.get("cgpa") or 0),
        "payment_date": request.form.get("payment_date"),
        "prefs": [r for r in ROOM_TYPES if request.form.get(f"pref_{r}")],
    }

    data["students"].append(student)
    write_data(data)
    return redirect(url_for("index", section="students"))


@app.route("/rooms", methods=["POST"])
def add_room():
    if not is_logged_in():
        return redirect(url_for("login"))

    data = read_data()

    room = {
        "id": request.form.get("id"),
        "type": request.form.get("type"),
        "yearGroup": request.form.get("year_group"),
        "capacity": int(request.form.get("capacity", 1)),
        "occupied": 0,
        "residents": [],
        "gender": None,
    }

    data["rooms"].append(room)
    write_data(data)
    return redirect(url_for("index", section="rooms"))


@app.route("/allocate", methods=["POST"])
def allocate():
    if not is_logged_in():
        return redirect(url_for("login"))

    data = read_data()
    execute_allocation(data)
    write_data(data)
    return redirect(url_for("index", section="engine"))




# Export allocation report as plain text
@app.route("/export")
def export_allocation():
    if not is_logged_in():
        return redirect(url_for("login"))

    data = read_data()

    report = "HOSTEL ALLOCATION REPORT\n"
    report += "========================\n\n"

    for room in data["rooms"]:
        residents = ", ".join(room["residents"]) if room["residents"] else "EMPTY"
        gender = room["gender"] if room["gender"] else "Unassigned"
        report += f"ROOM {room['id']} [{room['type']} - {room['yearGroup']} - {gender}]: {residents}\n"

    report += "\nWAITING LIST\n"

    for w in data["waiting"]:
        report += f"- {w['name']} ({w['gender']})\n"

    return Response(
        report,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment;filename=allocation_report.txt"}
    )


if __name__ == "__main__":
    if not DATA_FILE.exists():
        write_data(default_data())
    app.run(debug=True)
