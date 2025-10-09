import os
from datetime import datetime, date, time as dtime, timedelta
import pytz
from flask import Flask, render_template, request, redirect, url_for, session
import logging
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Google integrations
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

# Email
import smtplib
from email.message import EmailMessage
import hmac
import hashlib

# Load environment variables from .env if present
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
try:
    app.logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
except Exception:
    app.logger.setLevel(logging.INFO)

# Email configuration (optional)
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
EMAIL_FROM = os.getenv('EMAIL_FROM', SMTP_USERNAME or 'no-reply@example.com')
ADMIN_EMAILS = os.getenv('ADMIN_EMAILS', '')  # comma-separated list of owner/admin emails

# Fixed event configuration (30 minutes)
EVENT_NAME = os.getenv('EVENT_NAME', 'Intro Meeting')
EVENT_DURATION_MINUTES = int(os.getenv('EVENT_DURATION_MINUTES', '30'))
EVENT_DESCRIPTION = os.getenv('EVENT_DESCRIPTION', 'A 30-minute meeting to connect.')
BRAND_COMPANY = os.getenv('BRAND_COMPANY', 'Your Company')
BRAND_LOGO_URL = os.getenv('BRAND_LOGO_URL', '')  # Optional

# Initialize DB
db = SQLAlchemy(app)

class IntegrationToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)  # 'google'
    token_json = db.Column(db.Text, nullable=False)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    guests = db.Column(db.String(500), nullable=True)  # comma-separated emails
    notes = db.Column(db.Text, nullable=True)
    timezone = db.Column(db.String(64), nullable=False, default='UTC')
    start_utc = db.Column(db.DateTime, nullable=False)
    end_utc = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')  # active|cancelled

class BookingIntegration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)  # e.g., 'google'
    booking_id = db.Column(db.Integer, nullable=False)
    external_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class CalendarSyncState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)  # e.g., 'google'
    calendar_id = db.Column(db.String(255), nullable=False, default='primary')
    sync_token = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class AvailabilityWindow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # 0=Monday ... 6=Sunday
    weekday = db.Column(db.Integer, nullable=False)
    start_minutes = db.Column(db.Integer, nullable=False)  # minutes from 00:00
    end_minutes = db.Column(db.Integer, nullable=False)    # minutes from 00:00

    @staticmethod
    def seed_defaults():
        # Default: Mon-Fri 09:00-17:00
        if AvailabilityWindow.query.count() == 0:
            for weekday in range(0, 5):
                db.session.add(AvailabilityWindow(
                    weekday=weekday,
                    start_minutes=9*60,
                    end_minutes=17*60
                ))
            db.session.commit()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

scheduler = BackgroundScheduler()


def start_scheduler_once():
    if not scheduler.running:
        scheduler.start()


from sqlalchemy import inspect, text

HAS_BOOKING_STATUS = False

def _has_column(table: str, column: str) -> bool:
    try:
        insp = inspect(db.engine)
        cols = [c['name'] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False

def init_db():
    db.create_all()
    # Attempt to add missing status column (sqlite only) for soft-cancel support
    global HAS_BOOKING_STATUS
    try:
        HAS_BOOKING_STATUS = _has_column('booking', 'status')
        if not HAS_BOOKING_STATUS:
            if db.engine.url.drivername.startswith('sqlite'):
                app.logger.info('Adding missing column booking.status for soft delete support')
                try:
                    db.session.execute(text("ALTER TABLE booking ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"))
                    db.session.commit()
                    HAS_BOOKING_STATUS = True
                except Exception as e:
                    app.logger.error('Failed to add booking.status column: %s', e)
                    db.session.rollback()
            else:
                app.logger.warning('booking.status column missing; please run a migration in your DB')
    except Exception as e:
        app.logger.error('Error checking/adding booking.status column: %s', e)
    AvailabilityWindow.seed_defaults()
    # Start scheduler when app first handles a request
    start_scheduler_once()

# Initialize DB at import time (Flask 3.0 removed before_first_request)
with app.app_context():
    init_db()

# Helpers

def list_timezones():
    # Reasonable subset: use common_timezones
    return pytz.common_timezones

def parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, '%Y-%m-%d').date()

def parse_time(time_str: str) -> dtime:
    return datetime.strptime(time_str, '%H:%M').time()

def minutes_of_day(t: dtime) -> int:
    return t.hour * 60 + t.minute

def generate_slots_for_date(the_date: date, tz_name: str):
    tz = pytz.timezone(tz_name)
    weekday = the_date.weekday()  # 0=Mon ... 6=Sun
    windows = AvailabilityWindow.query.filter_by(weekday=weekday).all()

    # Get all bookings on this date (overlapping)
    day_start_local = tz.localize(datetime.combine(the_date, dtime.min))
    day_end_local = tz.localize(datetime.combine(the_date, dtime.max))
    day_start_utc = day_start_local.astimezone(pytz.UTC)
    day_end_utc = day_end_local.astimezone(pytz.UTC)

    q = Booking.query.filter(Booking.start_utc < day_end_utc, Booking.end_utc > day_start_utc)
    # Filter out cancelled bookings if the column exists
    try:
        if HAS_BOOKING_STATUS:
            q = q.filter(Booking.status != 'cancelled')
    except Exception:
        pass
    bookings = q.all()

    # Build a set of blocked UTC intervals
    blocked = [(b.start_utc, b.end_utc) for b in bookings]

    slots = []
    for w in windows:
        start_min = w.start_minutes
        end_min = w.end_minutes
        cursor = start_min
        step = EVENT_DURATION_MINUTES
        while cursor + step <= end_min:
            start_local = tz.localize(datetime.combine(the_date, dtime(hour=cursor // 60, minute=cursor % 60)))
            end_local = start_local + timedelta(minutes=step)
            start_u = start_local.astimezone(pytz.UTC)
            end_u = end_local.astimezone(pytz.UTC)

            # Check overlap with blocked intervals
            is_free = True
            for b_start, b_end in blocked:
                if not (end_u <= b_start or start_u >= b_end):
                    is_free = False
                    break
            if is_free:
                # Return label in local time
                slots.append({
                    'label': start_local.strftime('%-I:%M %p') if os.name != 'nt' else start_local.strftime('%I:%M %p').lstrip('0'),
                    'value': start_local.strftime('%H:%M')
                })
            cursor += step
    return slots

# Routes

@app.route('/')
def root():
    return redirect(url_for('event_30'))

@app.route('/meet/30')
def event_30():
    # Step 1: Date selection
    tz = request.args.get('tz') or session.get('tz') or 'UTC'
    session['tz'] = tz
    today = datetime.utcnow().date()
    return render_template('date_select.html',
                           tz=tz,
                           timezones=list_timezones(),
                           today=today,
                           event_name=EVENT_NAME,
                           event_description=EVENT_DESCRIPTION,
                           brand_company=BRAND_COMPANY,
                           brand_logo_url=BRAND_LOGO_URL)

@app.route('/meet/30/times')
def event_30_times():
    # Step 2: Time selection for selected date
    tz = request.args.get('tz') or session.get('tz') or 'UTC'
    session['tz'] = tz
    date_str = request.args.get('date')
    if not date_str:
        return redirect(url_for('event_30'))
    the_date = parse_date(date_str)
    slots = generate_slots_for_date(the_date, tz)

    # Human-readable date header
    tz_obj = pytz.timezone(tz)
    hdr_dt = tz_obj.localize(datetime.combine(the_date, dtime(12, 0)))
    date_header = hdr_dt.strftime('%A, %B %d, %Y')

    return render_template('time_select.html',
                           tz=tz,
                           date_str=date_str,
                           date_header=date_header,
                           slots=slots,
                           event_name=EVENT_NAME,
                           event_description=EVENT_DESCRIPTION,
                           brand_company=BRAND_COMPANY,
                           brand_logo_url=BRAND_LOGO_URL)

@app.route('/meet/30/details', methods=['GET', 'POST'])
def event_30_details():
    tz = request.args.get('tz') or session.get('tz') or 'UTC'
    session['tz'] = tz

    if request.method == 'POST':
        date_str = request.form['date']
        time_str = request.form['time']
        name = request.form['name']
        email = request.form['email']
        guests = request.form.get('guests') or ''
        notes = request.form.get('notes') or ''

        the_date = parse_date(date_str)
        the_time = parse_time(time_str)

        tz_obj = pytz.timezone(tz)
        start_local = tz_obj.localize(datetime.combine(the_date, the_time))
        end_local = start_local + timedelta(minutes=EVENT_DURATION_MINUTES)
        start_utc = start_local.astimezone(pytz.UTC)
        end_utc = end_local.astimezone(pytz.UTC)

        booking = Booking(
            name=name,
            email=email,
            guests=guests,
            notes=notes,
            timezone=tz,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        db.session.add(booking)
        db.session.commit()

        # Attempt Google Calendar event creation (optional)
        try:
            create_google_calendar_event(booking)
        except Exception:
            # Ignore integration failures for now
            pass

        # Notify admins/owners about the new booking (non-blocking)
        try:
            send_admin_notification(booking, 'booked')
        except Exception:
            pass

        # Send confirmation email (optional)
        try:
            send_confirmation_email(booking)
        except Exception:
            pass

        # Schedule reminder 30 minutes before
        try:
            schedule_reminder_email(booking, minutes_before=30)
        except Exception:
            pass

        return redirect(url_for('event_30_confirmation', booking_id=booking.id))

    # GET: show form with summary
    date_str = request.args.get('date')
    time_str = request.args.get('time')
    if not date_str or not time_str:
        return redirect(url_for('event_30'))

    tz_obj = pytz.timezone(tz)
    the_date = parse_date(date_str)
    the_time = parse_time(time_str)
    start_local = tz_obj.localize(datetime.combine(the_date, the_time))
    end_local = start_local + timedelta(minutes=EVENT_DURATION_MINUTES)

    # Human-readable summary
    time_range = f"{start_local.strftime('%-I:%M %p') if os.name != 'nt' else start_local.strftime('%I:%M %p').lstrip('0')} - " \
                 f"{end_local.strftime('%-I:%M %p') if os.name != 'nt' else end_local.strftime('%I:%M %p').lstrip('0')}"
    date_header = start_local.strftime('%A, %B %d, %Y')

    return render_template('details.html',
                           tz=tz,
                           date_str=date_str,
                           time_str=time_str,
                           time_range=time_range,
                           date_header=date_header,
                           event_name=EVENT_NAME,
                           event_description=EVENT_DESCRIPTION,
                           brand_company=BRAND_COMPANY,
                           brand_logo_url=BRAND_LOGO_URL)

@app.route('/meet/30/confirmation/<int:booking_id>')
def event_30_confirmation(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)
    tz = booking.timezone
    tz_obj = pytz.timezone(tz)
    start_local = booking.start_utc.astimezone(tz_obj)
    end_local = booking.end_utc.astimezone(tz_obj)
    time_range = f"{start_local.strftime('%-I:%M %p') if os.name != 'nt' else start_local.strftime('%I:%M %p').lstrip('0')} - " \
                 f"{end_local.strftime('%-I:%M %p') if os.name != 'nt' else end_local.strftime('%I:%M %p').lstrip('0')}"
    date_header = start_local.strftime('%A, %B %d, %Y')

    return render_template('confirmation.html',
                           booking=booking,
                           tz=tz,
                           time_range=time_range,
                           date_header=date_header,
                           event_name=EVENT_NAME,
                           event_description=EVENT_DESCRIPTION,
                           brand_company=BRAND_COMPANY,
                           brand_logo_url=BRAND_LOGO_URL)

# --- Email sending ---

def send_email(to_email: str, subject: str, body: str):
    if not EMAIL_ENABLED:
        return
    if not (SMTP_HOST and SMTP_PORT and SMTP_USERNAME and SMTP_PASSWORD):
        return
    msg = EmailMessage()
    msg['From'] = EMAIL_FROM
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.set_content(body)

    # Use SMTP_SSL for port 465, SMTP with starttls for other ports
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)


def send_confirmation_email(booking: Booking):
    tz_obj = pytz.timezone(booking.timezone)
    start_local = booking.start_utc.astimezone(tz_obj)
    end_local = booking.end_utc.astimezone(tz_obj)
    subject = f"Confirmed: {EVENT_NAME} on {start_local.strftime('%b %d, %Y')}"
    body = (
        f"Hi {booking.name},\n\n"
        f"You're scheduled for {EVENT_NAME}.\n\n"
        f"When: {start_local.strftime('%A, %B %d, %Y %I:%M %p')} - {end_local.strftime('%I:%M %p')} ({booking.timezone})\n"
        f"Description: {EVENT_DESCRIPTION}\n\n"
        f"Notes: {booking.notes or 'N/A'}\n\n"
        f"If you need to reschedule, please reply to this email.\n"
    )

# --- Admin email notifications ---

def _admin_recipients() -> list[str]:
    raw = ADMIN_EMAILS or ''
    return [e.strip() for e in raw.split(',') if e.strip()]

def _format_booking_window(booking: Booking) -> str:
    tz_obj = pytz.timezone(booking.timezone)
    start_local = booking.start_utc.astimezone(tz_obj)
    end_local = booking.end_utc.astimezone(tz_obj)
    start_str = start_local.strftime('%A, %B %d, %Y %I:%M %p')
    end_str = end_local.strftime('%I:%M %p')
    if os.name == 'nt':
        # Strip leading zero quirks on Windows
        if start_str.startswith('0'):
            start_str = start_str[1:]
        if end_str.startswith('0'):
            end_str = end_str[1:]
    return f"{start_str} — {end_str} ({booking.timezone})"

def send_admin_notification(booking: Booking, action: str, previous: str | None = None):
    if not EMAIL_ENABLED:
        return
    recipients = _admin_recipients()
    if not recipients:
        return

    window = _format_booking_window(booking)
    subject = f"[{BRAND_COMPANY}] {EVENT_NAME} {action.capitalize()}"

    lines = [
        f"Event: {EVENT_NAME}",
        f"Action: {action}",
        f"When: {window}",
        f"Booker: {booking.name} <{booking.email}>",
    ]
    if booking.guests:
        lines.append(f"Guests: {booking.guests}")
    if booking.notes:
        lines.append(f"Notes: {booking.notes}")
    if previous:
        lines.append(f"Previous time: {previous}")

    body = "\n".join(lines)

    for r in recipients:
        try:
            send_email(r, subject, body)
        except Exception:
            # Non-blocking; consider logging
            pass

# --- Attendee self-service security helpers ---

def _booking_token(booking: Booking) -> str:
    secret = (app.config.get('SECRET_KEY') or 'dev-secret-change-me').encode('utf-8')
    payload = f"b:{booking.id}:{int(booking.created_at.timestamp())}".encode('utf-8')
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()

def _verify_booking_token(booking: Booking, token: str) -> bool:
    try:
        expected = _booking_token(booking)
        return hmac.compare_digest(expected, token or '')
    except Exception:
        return False
    send_email(booking.email, subject, body)


def schedule_reminder_email(booking: Booking, minutes_before: int = 30):
    if not EMAIL_ENABLED:
        return
    trigger_time = booking.start_utc - timedelta(minutes=minutes_before)
    if trigger_time <= datetime.utcnow():
        return

    def job(booking_id: int):
        b = Booking.query.get(booking_id)
        if not b:
            return
        tz_obj = pytz.timezone(b.timezone)
        start_local = b.start_utc.astimezone(tz_obj)
        subject = f"Reminder: {EVENT_NAME} in {minutes_before} minutes"
        body = (
            f"Hi {b.name},\n\n"
            f"This is a reminder for your upcoming {EVENT_NAME} at {start_local.strftime('%I:%M %p')} ({b.timezone}) on {start_local.strftime('%b %d, %Y')}.\n\n"
            f"See you soon!\n"
        )
        send_email(b.email, subject, body)

    scheduler.add_job(
        func=job,
        trigger=DateTrigger(run_date=trigger_time),
        args=[booking.id],
        id=f"reminder-{booking.id}",
        replace_existing=True,
        misfire_grace_time=300,
    )

# --- Google Calendar Integration ---

SCOPES = ['https://www.googleapis.com/auth/calendar']
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')
CLIENT_SECRETS_FILE = os.getenv('GOOGLE_CLIENT_SECRETS_FILE', 'google_client_secret.json')


def get_google_credentials() -> Credentials | None:
    rec = IntegrationToken.query.filter_by(provider='google').first()
    if not rec:
        return None
    creds = Credentials.from_authorized_user_info(eval(rec.token_json))
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_google_credentials(creds)
    return creds


def save_google_credentials(creds: Credentials):
    rec = IntegrationToken.query.filter_by(provider='google').first()
    data = creds.to_json()
    if rec:
        rec.token_json = data
    else:
        rec = IntegrationToken(provider='google', token_json=data)
        db.session.add(rec)
    db.session.commit()


def create_google_calendar_event(booking: Booking):
    creds = get_google_credentials()
    if not creds:
        return
    tz_name = booking.timezone
    tz_obj = pytz.timezone(tz_name)
    start_local = booking.start_utc.astimezone(tz_obj)
    end_local = booking.end_utc.astimezone(tz_obj)

    attendees = [{'email': booking.email}]
    if booking.guests:
        for g in booking.guests.split(','):
            em = g.strip()
            if em:
                attendees.append({'email': em})

    body = {
        'summary': EVENT_NAME,
        'description': (EVENT_DESCRIPTION + '\n\n' + (booking.notes or '')).strip(),
        'start': {'dateTime': start_local.isoformat(), 'timeZone': tz_name},
        'end': {'dateTime': end_local.isoformat(), 'timeZone': tz_name},
        'attendees': attendees,
        'conferenceData': {
            'createRequest': {
                'requestId': f'booking-{booking.id}'
            }
        }
    }

    service = build('calendar', 'v3', credentials=creds)
    event = service.events().insert(
        calendarId='primary',
        body=body,
        conferenceDataVersion=1,
        sendUpdates='all'
    ).execute()
    try:
        event_id = event.get('id')
        if event_id:
            # Upsert mapping
            rec = BookingIntegration.query.filter_by(provider='google', booking_id=booking.id).first()
            if rec:
                rec.external_id = event_id
            else:
                db.session.add(BookingIntegration(provider='google', booking_id=booking.id, external_id=event_id))
            db.session.commit()
    except Exception:
        pass
    return event

def update_google_calendar_event(booking: Booking):
    creds = get_google_credentials()
    if not creds:
        return
    rec = BookingIntegration.query.filter_by(provider='google', booking_id=booking.id).first()
    if not rec:
        # If no mapping exists, create a fresh event and map it
        try:
            create_google_calendar_event(booking)
        except Exception:
            pass
        return

    tz_name = booking.timezone
    tz_obj = pytz.timezone(tz_name)
    start_local = booking.start_utc.astimezone(tz_obj)
    end_local = booking.end_utc.astimezone(tz_obj)

    body = {
        'summary': EVENT_NAME,
        'description': (EVENT_DESCRIPTION + '\n\n' + (booking.notes or '')).strip(),
        'start': {'dateTime': start_local.isoformat(), 'timeZone': tz_name},
        'end': {'dateTime': end_local.isoformat(), 'timeZone': tz_name},
    }

    service = build('calendar', 'v3', credentials=creds)
    try:
        service.events().patch(
            calendarId='primary',
            eventId=rec.external_id,
            body=body,
            sendUpdates='all'
        ).execute()
    except Exception:
        # If patch fails (e.g., deleted externally), try to recreate and update mapping
        try:
            ev = create_google_calendar_event(booking)
            if ev and ev.get('id'):
                rec.external_id = ev['id']
                db.session.commit()
        except Exception:
            pass

def delete_google_calendar_event(booking: Booking):
    creds = get_google_credentials()
    if not creds:
        return
    rec = BookingIntegration.query.filter_by(provider='google', booking_id=booking.id).first()
    if not rec:
        return
    service = build('calendar', 'v3', credentials=creds)
    try:
        service.events().delete(
            calendarId='primary',
            eventId=rec.external_id,
            sendUpdates='all'
        ).execute()
    except Exception:
        pass
    # Remove mapping regardless
    try:
        db.session.delete(rec)
        db.session.commit()
    except Exception:
        pass

# --- Google Calendar polling sync (delta with syncToken) ---

def _get_or_create_sync_state() -> CalendarSyncState:
    rec = CalendarSyncState.query.filter_by(provider='google', calendar_id='primary').first()
    if not rec:
        rec = CalendarSyncState(provider='google', calendar_id='primary')
        db.session.add(rec)
        db.session.commit()
    return rec

def _parse_event_dt(part: dict) -> tuple[datetime, str] | None:
    # Returns (aware_dt, tz_name)
    if not part:
        return None
    dt_str = part.get('dateTime')
    tz_name = part.get('timeZone') or 'UTC'
    if not dt_str:
        # All-day events (date) are not expected for app-created events; skip
        return None
    # Normalize 'Z' to '+00:00'
    try:
        s = dt_str.replace('Z', '+00:00')
        aware = datetime.fromisoformat(s)
        if aware.tzinfo is None:
            aware = pytz.timezone(tz_name).localize(aware)
        return aware, tz_name
    except Exception:
        return None

def _process_google_event_change(event: dict):
    ev_id = event.get('id')
    status = event.get('status')
    if not ev_id:
        return
    link = BookingIntegration.query.filter_by(provider='google', external_id=ev_id).first()
    if not link:
        return
    booking = Booking.query.get(link.booking_id)
    if not booking:
        return

    if status == 'cancelled':
        try:
            send_admin_notification(booking, 'cancelled')
        except Exception:
            app.logger.exception('Error sending admin notification for external cancel booking %s', booking.id)
        try:
            # Remove integration mapping then soft-cancel booking
            db.session.delete(link)
            if HAS_BOOKING_STATUS:
                booking.status = 'cancelled'
            else:
                db.session.delete(booking)
            db.session.commit()
            app.logger.info('Processed Google cancellation for booking %s', booking.id)
        except Exception:
            app.logger.exception('Error processing Google cancellation for booking %s', booking.id)
        return

    start = _parse_event_dt(event.get('start'))
    end = _parse_event_dt(event.get('end'))
    if not (start and end):
        return
    start_dt, tz_name = start
    end_dt, _ = end

    prev_window = _format_booking_window(booking)
    try:
        booking.timezone = tz_name or booking.timezone
        booking.start_utc = start_dt.astimezone(pytz.UTC)
        booking.end_utc = end_dt.astimezone(pytz.UTC)
        if HAS_BOOKING_STATUS and booking.status == 'cancelled':
            booking.status = 'active'
        db.session.commit()
        app.logger.info('Processed Google reschedule for booking %s', booking.id)
    except Exception:
        app.logger.exception('Error updating booking from Google change %s', booking.id)
        return

    try:
        send_admin_notification(booking, 'rescheduled', previous=prev_window)
    except Exception:
        app.logger.exception('Error sending admin reschedule notification for booking %s', booking.id)

def sync_google_calendar_changes():
    with app.app_context():
        creds = get_google_credentials()
        if not creds:
            app.logger.debug('Google sync: no credentials; skipping')
            return
        service = build('calendar', 'v3', credentials=creds)
        state = _get_or_create_sync_state()
        page_token = None
        next_sync_token = None
        processed = 0
        try:
            while True:
                if state.sync_token:
                    req = service.events().list(
                        calendarId='primary',
                        syncToken=state.sync_token,
                        showDeleted=True,
                        singleEvents=True,
                        pageToken=page_token
                    )
                else:
                    time_min = (datetime.utcnow() - timedelta(days=90)).isoformat() + 'Z'
                    req = service.events().list(
                        calendarId='primary',
                        timeMin=time_min,
                        singleEvents=True,
                        showDeleted=True,
                        pageToken=page_token,
                        maxResults=2500
                    )
                resp = req.execute()
                for ev in resp.get('items', []):
                    _process_google_event_change(ev)
                    processed += 1
                page_token = resp.get('nextPageToken')
                if not page_token:
                    next_sync_token = resp.get('nextSyncToken')
                    break
        except HttpError as e:
            # 410 Gone indicates sync token is invalid; reset and try fresh next run
            try:
                if getattr(e, 'resp', None) and getattr(e.resp, 'status', None) == 410:
                    state.sync_token = None
                    state.updated_at = datetime.utcnow()
                    db.session.commit()
                    app.logger.warning('Google sync: sync token invalidated (410). Will reseed next run')
                    return
            except Exception:
                pass
            app.logger.exception('Google sync: HttpError during sync')
            return
        except Exception:
            app.logger.exception('Google sync: unexpected error during sync')
            return

        if next_sync_token:
            try:
                state.sync_token = next_sync_token
                state.updated_at = datetime.utcnow()
                db.session.commit()
                app.logger.info('Google sync: processed %s changes; token advanced', processed)
            except Exception:
                app.logger.exception('Google sync: failed to persist next sync token')

def start_google_sync_poll():
    try:
        minutes = int(os.getenv('GOOGLE_SYNC_INTERVAL_MINUTES', '2'))
        scheduler.add_job(
            sync_google_calendar_changes,
            'interval',
            minutes=minutes,
            id='google_sync_poll',
            replace_existing=True,
            misfire_grace_time=60,
        )
    except Exception:
        pass

@app.route('/integrations')
def integrations_home():
    creds = get_google_credentials()
    return render_template('integrations.html', google_connected=bool(creds))

# Lightweight availability API for UI calendar
@app.route('/api/availability')
def api_availability():
    try:
        year = int(request.args.get('year'))
        month = int(request.args.get('month'))  # 1-12
        tz = request.args.get('tz') or 'UTC'
    except Exception:
        return {'error': 'Invalid parameters'}, 400

    # Determine number of days in month
    first = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    days = (next_month - first).days

    results = []
    for day in range(1, days + 1):
        d = date(year, month, day)
        slots = generate_slots_for_date(d, tz)
        results.append({'date': d.isoformat(), 'has_slots': len(slots) > 0})

    return {'days': results}

@app.route('/auth/google')
def auth_google():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=f"{BASE_URL}/oauth2callback"
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=f"{BASE_URL}/oauth2callback"
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    save_google_credentials(creds)
    return redirect(url_for('integrations_home'))

# --- Admin: Availability Management ---

def minutes_to_str(m: int) -> str:
    h = m // 60
    mi = m % 60
    return f"{h:02d}:{mi:02d}"

@app.route('/admin/availability', methods=['GET', 'POST'])
def admin_availability():
    # Simple token protection; set ADMIN_TOKEN in .env for write access
    admin_token = os.getenv('ADMIN_TOKEN')
    token = request.args.get('token') or request.form.get('token')

    weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

    if request.method == 'POST':
        if admin_token and token != admin_token:
            return "Unauthorized", 401
        # Expect fields: start_0, end_0, ..., start_6, end_6 (HH:MM)
        for wd in range(7):
            s = request.form.get(f'start_{wd}', '').strip()
            e = request.form.get(f'end_{wd}', '').strip()
            existing = AvailabilityWindow.query.filter_by(weekday=wd).all()
            # Remove existing to re-add if valid
            for ex in existing:
                db.session.delete(ex)
            if s and e:
                try:
                    sh, sm = [int(x) for x in s.split(':')]
                    eh, em = [int(x) for x in e.split(':')]
                    db.session.add(AvailabilityWindow(
                        weekday=wd,
                        start_minutes=sh*60+sm,
                        end_minutes=eh*60+em
                    ))
                except Exception:
                    pass
        db.session.commit()
        return redirect(url_for('admin_availability', token=token))

    # GET: Build form values from DB
    rows = []
    for wd in range(7):
        rec = AvailabilityWindow.query.filter_by(weekday=wd).first()
        start_val = minutes_to_str(rec.start_minutes) if rec else ''
        end_val = minutes_to_str(rec.end_minutes) if rec else ''
        rows.append({
            'weekday_index': wd,
            'weekday_name': weekdays[wd],
            'start': start_val,
            'end': end_val,
        })

    return render_template('admin_availability.html', rows=rows, has_token=bool(admin_token))

# --- Admin: Booking Management (reschedule/cancel) ---

@app.route('/admin/bookings/<int:booking_id>/reschedule', methods=['POST'])
def admin_reschedule_booking(booking_id: int):
    admin_token = os.getenv('ADMIN_TOKEN')
    token = request.args.get('token') or request.form.get('token')
    if admin_token and token != admin_token:
        return "Unauthorized", 401

    booking = Booking.query.get_or_404(booking_id)

    prev_window = _format_booking_window(booking)

    tz = request.form.get('tz') or booking.timezone
    date_str = request.form.get('date')
    time_str = request.form.get('time')
    if not (date_str and time_str):
        return {"error": "Missing date/time"}, 400

    the_date = parse_date(date_str)
    the_time = parse_time(time_str)
    tz_obj = pytz.timezone(tz)
    start_local = tz_obj.localize(datetime.combine(the_date, the_time))
    end_local = start_local + timedelta(minutes=EVENT_DURATION_MINUTES)

    booking.timezone = tz
    booking.start_utc = start_local.astimezone(pytz.UTC)
    booking.end_utc = end_local.astimezone(pytz.UTC)
    if HAS_BOOKING_STATUS and booking.status == 'cancelled':
        booking.status = 'active'
    db.session.commit()

    # Try to update Google Calendar event if integration available
    try:
        update_google_calendar_event(booking)
    except Exception:
        app.logger.exception('Error updating Google event for admin reschedule booking %s', booking_id)

    try:
        send_admin_notification(booking, 'rescheduled', previous=prev_window)
    except Exception:
        app.logger.exception('Error sending admin notification for admin reschedule booking %s', booking_id)

    return {"ok": True}

@app.route('/admin/bookings/<int:booking_id>/cancel', methods=['POST'])
def admin_cancel_booking(booking_id: int):
    admin_token = os.getenv('ADMIN_TOKEN')
    token = request.args.get('token') or request.form.get('token')
    if admin_token and token != admin_token:
        return "Unauthorized", 401

    booking = Booking.query.get_or_404(booking_id)

    # Try to delete Google Calendar event first so we still have details
    try:
        delete_google_calendar_event(booking)
    except Exception:
        app.logger.exception('Error deleting Google Calendar event for booking %s', booking_id)

    try:
        send_admin_notification(booking, 'cancelled')
    except Exception:
        app.logger.exception('Error sending admin notification for cancelled booking %s', booking_id)

    # Soft cancel if possible; fall back to delete
    try:
        if HAS_BOOKING_STATUS:
            booking.status = 'cancelled'
            db.session.commit()
        else:
            db.session.delete(booking)
            db.session.commit()
    except Exception:
        app.logger.exception('Error cancelling booking %s', booking_id)

    return {"ok": True}

# --- Attendee: Booking reschedule (public via token) ---

@app.route('/meet/bookings/<int:booking_id>/reschedule', methods=['POST'])
def attendee_reschedule_booking(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)

    token = request.args.get('token') or request.form.get('token')
    if not _verify_booking_token(booking, token):
        return {"error": "Unauthorized"}, 401

    prev_window = _format_booking_window(booking)

    tz = request.form.get('tz') or booking.timezone
    date_str = request.form.get('date')
    time_str = request.form.get('time')
    if not (date_str and time_str):
        return {"error": "Missing date/time"}, 400

    the_date = parse_date(date_str)
    the_time = parse_time(time_str)
    tz_obj = pytz.timezone(tz)
    start_local = tz_obj.localize(datetime.combine(the_date, the_time))
    end_local = start_local + timedelta(minutes=EVENT_DURATION_MINUTES)

    booking.timezone = tz
    booking.start_utc = start_local.astimezone(pytz.UTC)
    booking.end_utc = end_local.astimezone(pytz.UTC)
    if HAS_BOOKING_STATUS and booking.status == 'cancelled':
        booking.status = 'active'
    db.session.commit()

    # Update Google Calendar event to reflect new time
    try:
        update_google_calendar_event(booking)
    except Exception:
        app.logger.exception('Error updating Google event for attendee reschedule booking %s', booking_id)

    # Notify admins
    try:
        send_admin_notification(booking, 'rescheduled', previous=prev_window)
    except Exception:
        app.logger.exception('Error sending admin notification for attendee reschedule booking %s', booking_id)

    return {"ok": True}

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=True)
else:
    # Start Google sync polling when running under a WSGI server as well
    with app.app_context():
        start_google_sync_poll()
