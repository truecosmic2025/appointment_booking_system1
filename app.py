import os
from datetime import datetime, date, time as dtime, timedelta
import pytz
from flask import Flask, render_template, request, redirect, url_for, session
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

# Load environment variables from .env if present
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration (optional)
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
EMAIL_FROM = os.getenv('EMAIL_FROM', SMTP_USERNAME or 'no-reply@example.com')

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


def init_db():
    db.create_all()
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

    bookings = Booking.query.filter(Booking.start_utc < day_end_utc, Booking.end_utc > day_start_utc).all()

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
    return event

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

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=True)
