from datetime import datetime
from app import db


class CoachAvatar(db.Model):
    """Copy of a coach's photo URL from the coaches site, so pages never wait on that site."""
    __tablename__ = "coach_avatar"
    site_slug = db.Column(db.String(120), primary_key=True)  # slug on coaches.truecosmic.com
    name_key = db.Column(db.String(200), index=True, nullable=False, default="")
    image_url = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
