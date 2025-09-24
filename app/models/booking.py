from datetime import datetime
from app import db


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    visitor_name = db.Column(db.String(120), nullable=False)
    visitor_email = db.Column(db.String(255), nullable=False, index=True)
    start_utc = db.Column(db.DateTime, nullable=False, index=True)
    end_utc = db.Column(db.DateTime, nullable=False)
    timezone = db.Column(db.String(64), default='UTC', nullable=False)
    status = db.Column(db.String(20), default='booked', nullable=False)  # booked, cancelled
    google_event_id = db.Column(db.String(255), nullable=True)
    meet_link = db.Column(db.String(512), nullable=True)
    token = db.Column(db.String(64), nullable=False, index=True)  # for reschedule/cancel links
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coach = db.relationship('User')

