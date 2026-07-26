import random
from datetime import datetime

from flask import Blueprint, jsonify, request
from email_validator import EmailNotValidError, validate_email
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Customer, Reservation

reservations_bp = Blueprint("reservations", __name__)


def _parse_time_slot(raw_value):
    """Accepts ISO 8601 strings (e.g. 2026-08-14T19:30) from the React date/time inputs."""
    try:
        return datetime.fromisoformat(raw_value)
    except (TypeError, ValueError):
        return None


@reservations_bp.route("/api/reservations", methods=["POST"])
def create_reservation():
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip() or None
    guests = data.get("guests")
    time_slot_raw = data.get("time_slot")
    newsletter_opt_in = bool(data.get("newsletter_signup", False))

    errors = {}
    if not name:
        errors["name"] = "Full name is required."
    if not email:
        errors["email"] = "Email is required."
    else:
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError:
            errors["email"] = "Please enter a valid email address."

    time_slot = _parse_time_slot(time_slot_raw)
    if time_slot is None:
        errors["time_slot"] = "A valid date and time slot is required."

    try:
        guests = int(guests)
        if guests < 1:
            raise ValueError
    except (TypeError, ValueError):
        errors["guests"] = "Number of guests must be a positive integer."

    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    total_tables = int(request.environ.get("TOTAL_TABLES", 30)) if request.environ.get("TOTAL_TABLES") else 30
    from flask import current_app

    total_tables = current_app.config.get("TOTAL_TABLES", 30)

    # Which tables are already booked for this exact time slot?
    taken = {
        r.table_number
        for r in Reservation.query.filter_by(time_slot=time_slot).all()
    }
    available_tables = [t for t in range(1, total_tables + 1) if t not in taken]

    if not available_tables:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"That time is fully booked. {time_slot.strftime('%I:%M %p')} is unavailable "
                    f"for {guests} guests on {time_slot.strftime('%b %d, %Y')}. Please choose another slot.",
                }
            ),
            409,
        )

    # Look up an existing customer by email, otherwise create one.
    customer = Customer.query.filter_by(customer_email=email).first()
    if customer is None:
        customer = Customer(
            customer_name=name,
            customer_email=email,
            phone_number=phone,
            newsletter_signup=newsletter_opt_in,
        )
        db.session.add(customer)
        db.session.flush()  # get customer_id before creating the reservation
    else:
        customer.customer_name = name
        customer.phone_number = phone or customer.phone_number
        customer.newsletter_signup = customer.newsletter_signup or newsletter_opt_in

    # NFR-5: prevent double/over booking even if two requests race for the same
    # slot. The (time_slot, table_number) unique constraint is the real guard;
    # here we just retry against the remaining candidate tables if we lose a race.
    random.shuffle(available_tables)
    reservation = None
    for candidate_table in available_tables:
        reservation = Reservation(
            customer_id=customer.customer_id,
            time_slot=time_slot,
            table_number=candidate_table,
            guests=guests,
        )
        db.session.add(reservation)
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            reservation = None
            continue

    if reservation is None:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"That time is fully booked. {time_slot.strftime('%I:%M %p')} is unavailable "
                    f"for {guests} guests on {time_slot.strftime('%b %d, %Y')}. Please choose another slot.",
                }
            ),
            409,
        )

    return (
        jsonify(
            {
                "success": True,
                "message": "Reservation confirmed.",
                "reservation": reservation.to_dict(),
                "table_number": reservation.table_number,
            }
        ),
        201,
    )


@reservations_bp.route("/api/reservations/availability", methods=["GET"])
def slot_availability():
    """Helper endpoint the frontend can call to gray out fully-booked slots for a given date."""
    from flask import current_app

    date_str = request.args.get("date")  # expects YYYY-MM-DD
    if not date_str:
        return jsonify({"error": "date query param (YYYY-MM-DD) is required"}), 400

    total_tables = current_app.config.get("TOTAL_TABLES", 30)

    counts = {}
    reservations = Reservation.query.filter(
        db.func.date(Reservation.time_slot) == date_str
    ).all()
    for r in reservations:
        key = r.time_slot.strftime("%H:%M")
        counts[key] = counts.get(key, 0) + 1

    full_slots = [slot for slot, count in counts.items() if count >= total_tables]
    return jsonify({"date": date_str, "full_slots": full_slots, "total_tables": total_tables})
