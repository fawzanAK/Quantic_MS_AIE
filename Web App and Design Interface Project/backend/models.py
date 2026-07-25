from datetime import datetime

from extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    customer_id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_email = db.Column(db.String(255), nullable=False, index=True)
    phone_number = db.Column(db.String(30), nullable=True)
    newsletter_signup = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reservations = db.relationship("Reservation", backref="customer", lazy=True)

    def to_dict(self):
        return {
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "phone_number": self.phone_number,
            "newsletter_signup": self.newsletter_signup,
        }


class Reservation(db.Model):
    __tablename__ = "reservations"

    reservation_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"), nullable=False)
    time_slot = db.Column(db.DateTime, nullable=False, index=True)
    table_number = db.Column(db.Integer, nullable=False)
    guests = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "reservation_id": self.reservation_id,
            "customer_id": self.customer_id,
            "time_slot": self.time_slot.isoformat(),
            "table_number": self.table_number,
            "guests": self.guests,
        }


class NewsletterSignup(db.Model):
    """Standalone signups from users who subscribe without making a reservation."""

    __tablename__ = "newsletter_signups"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "email": self.email}
