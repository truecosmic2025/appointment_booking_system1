import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.auth.routes import roles_required
from app.models import CoachSettings, CoachProfile


coach_bp = Blueprint('coach', __name__, url_prefix='/coach')


@coach_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@roles_required('host', 'admin', 'owner')
def settings():
    profile = CoachProfile.query.filter_by(user_id=current_user.id).first()
    settings = CoachSettings.query.filter_by(user_id=current_user.id).first()
    if request.method == 'POST':
        tz = request.form.get('timezone', 'UTC').strip() or 'UTC'
        days = request.form.getlist('day')  # e.g., ['mon','tue']
        start = request.form.get('start', '09:00')
        end = request.form.get('end', '17:00')
        buffer_min = int(request.form.get('buffer_min', '0') or 0)
        min_notice_min = int(request.form.get('min_notice_min', '120') or 120)
        max_days_ahead = int(request.form.get('max_days_ahead', '30') or 30)

        # Persist timezone on profile
        if not profile:
            # create a minimal profile if missing
            profile = CoachProfile(user_id=current_user.id, slug=CoachProfile.generate_slug(current_user.name))
            db.session.add(profile)
        profile.timezone = tz

        # Build working hours JSON with one range per selected day
        hours = {}
        for d in ['mon','tue','wed','thu','fri','sat','sun']:
            if d in days:
                hours[d] = [[start, end]]
        wh_json = json.dumps(hours)

        if not settings:
            settings = CoachSettings(
                user_id=current_user.id,
                working_hours=wh_json,
                buffer_min=buffer_min,
                min_notice_min=min_notice_min,
                max_days_ahead=max_days_ahead,
            )
            db.session.add(settings)
        else:
            settings.working_hours = wh_json
            settings.buffer_min = buffer_min
            settings.min_notice_min = min_notice_min
            settings.max_days_ahead = max_days_ahead

        db.session.commit()
        flash('Availability settings saved.', 'success')
        return redirect(url_for('coach.settings'))

    # Defaults for form
    tz = profile.timezone if profile and profile.timezone else 'UTC'
    hours = {}
    if settings and settings.working_hours:
        try:
            hours = json.loads(settings.working_hours)
        except Exception:
            hours = {}
    selected_days = set(hours.keys()) if hours else set(['mon','tue','wed','thu','fri'])
    start = '09:00'
    end = '17:00'
    if hours:
        # take first available range from any day
        sample = next(iter(hours.values()))
        if sample and len(sample[0]) == 2:
            start, end = sample[0]

    return render_template(
        'coach/settings.html',
        tz=tz,
        selected_days=selected_days,
        start=start,
        end=end,
        buffer_min=settings.buffer_min if settings else 0,
        min_notice_min=settings.min_notice_min if settings else 120,
        max_days_ahead=settings.max_days_ahead if settings else 30,
    )

