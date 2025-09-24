from datetime import datetime
from slugify import slugify
from app import db


class CoachProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    timezone = db.Column(db.String(64), default='UTC', nullable=False)
    google_credentials = db.Column(db.Text, nullable=True)  # JSON credentials
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('coach_profile', uselist=False))

    @staticmethod
    def generate_slug(name: str) -> str:
        base = slugify(name) or 'coach'
        return base

