"""Persistent, one-time invitations for new coach accounts."""

from datetime import datetime, timedelta
import hashlib
import secrets

from app import db


class CoachInvite(db.Model):
    __tablename__ = "coach_invite"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    invited_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    accepted_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    accepted_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    inviter = db.relationship("User", foreign_keys=[invited_by_user_id])
    accepted_by = db.relationship("User", foreign_keys=[accepted_by_user_id])

    @staticmethod
    def token_hash_for(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def issue(cls, *, email: str, name: str, invited_by_user_id: int, expires_in_days: int = 7):
        """Create an invitation and return it with the only copy of its raw token."""
        token = secrets.token_urlsafe(32)
        invite = cls(
            email=email.strip().lower(),
            name=name.strip(),
            token_hash=cls.token_hash_for(token),
            invited_by_user_id=invited_by_user_id,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
        )
        return invite, token

    def is_usable(self, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        return self.accepted_at is None and self.expires_at > now
