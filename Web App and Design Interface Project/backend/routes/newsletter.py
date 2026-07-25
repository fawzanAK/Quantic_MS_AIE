from flask import Blueprint, jsonify, request
from email_validator import EmailNotValidError, validate_email

from extensions import db
from models import Customer, NewsletterSignup

newsletter_bp = Blueprint("newsletter", __name__)


@newsletter_bp.route("/api/newsletter", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()

    if not email:
        return jsonify({"success": False, "errors": {"email": "Email is required."}}), 400

    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return (
            jsonify({"success": False, "errors": {"email": "Please enter a valid email address."}}),
            400,
        )

    # If this email already belongs to a reservation customer, just flip the flag.
    customer = Customer.query.filter_by(customer_email=email).first()
    if customer is not None:
        customer.newsletter_signup = True
        db.session.commit()
        return jsonify({"success": True, "message": "You're subscribed."}), 200

    existing = NewsletterSignup.query.filter_by(email=email).first()
    if existing is not None:
        return jsonify({"success": True, "message": "You're already subscribed."}), 200

    signup_row = NewsletterSignup(email=email)
    db.session.add(signup_row)
    db.session.commit()

    return jsonify({"success": True, "message": "You're subscribed."}), 201
