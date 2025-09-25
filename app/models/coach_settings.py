from app import db


class CoachSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    # JSON string that maps weekday keys to list of [start,end] ranges, e.g. {"mon": [["09:00","17:00"]], ...}
    working_hours = db.Column(db.Text, nullable=True)
    buffer_min = db.Column(db.Integer, nullable=False, default=0)
    min_notice_min = db.Column(db.Integer, nullable=False, default=120)
    max_days_ahead = db.Column(db.Integer, nullable=False, default=30)

    user = db.relationship('User', backref=db.backref('coach_settings', uselist=False))

