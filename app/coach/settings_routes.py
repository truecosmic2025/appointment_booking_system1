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
        days = request.form.getlist('day')  # enabled days like ['mon','tue']
        buffer_min = int(request.form.get('buffer_min', '0') or 0)
        min_notice_min = int(request.form.get('min_notice_min', '120') or 120)
        max_days_ahead = int(request.form.get('max_days_ahead', '30') or 30)

        # Persist timezone on profile
        if not profile:
            # create a minimal profile if missing
            profile = CoachProfile(user_id=current_user.id, slug=CoachProfile.generate_slug(current_user.name))
            db.session.add(profile)
        profile.timezone = tz

        # Build working hours JSON with any number of ranges per selected day.
        # Each range is captured by repeated input names: start_<day> and end_<day>
        hours = {}
        for d in ['mon','tue','wed','thu','fri','sat','sun']:
            if d in days:
                starts = request.form.getlist(f'start_{d}')
                ends = request.form.getlist(f'end_{d}')
                d_ranges = []
                for s, e in zip(starts, ends):
                    s = (s or '').strip()
                    e = (e or '').strip()
                    if s and e and ':' in s and ':' in e:
                        d_ranges.append([s, e])
                if d_ranges:
                    hours[d] = d_ranges
        # Validate timezone
        try:
            import pytz
            pytz.timezone(tz)
        except Exception:
            flash('Invalid time zone. Please choose a valid IANA time zone (e.g., America/New_York).', 'error')
            return render_template(
                'coach/settings.html', tz=tz, hours=hours, selected_days=set(hours.keys()),
                buffer_min=buffer_min, min_notice_min=min_notice_min, max_days_ahead=max_days_ahead,
            )

        # Validate ranges: start < end and no overlaps within a day
        def to_minutes(hhmm: str) -> int:
            h, m = hhmm.split(':')
            return int(h) * 60 + int(m)

        for d, d_ranges in hours.items():
            # Clean and sort
            cleaned = []
            for s, e in d_ranges:
                try:
                    sm = to_minutes(s)
                    em = to_minutes(e)
                except Exception:
                    flash(f'Invalid time in {d.upper()} ranges.', 'error')
                    return render_template(
                        'coach/settings.html', tz=tz, hours=hours, selected_days=set(hours.keys()),
                        buffer_min=buffer_min, min_notice_min=min_notice_min, max_days_ahead=max_days_ahead,
                    )
                if em <= sm:
                    flash(f'End time must be after start time for {d.upper()} ranges.', 'error')
                    return render_template(
                        'coach/settings.html', tz=tz, hours=hours, selected_days=set(hours.keys()),
                        buffer_min=buffer_min, min_notice_min=min_notice_min, max_days_ahead=max_days_ahead,
                    )
                cleaned.append((sm, em))
            cleaned.sort()
            for i in range(1, len(cleaned)):
                prev_end = cleaned[i-1][1]
                cur_start = cleaned[i][0]
                if cur_start < prev_end:
                    flash(f'Overlapping ranges on {d.upper()}. Please adjust times.', 'error')
                    return render_template(
                        'coach/settings.html', tz=tz, hours=hours, selected_days=set(hours.keys()),
                        buffer_min=buffer_min, min_notice_min=min_notice_min, max_days_ahead=max_days_ahead,
                    )

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

    return render_template(
        'coach/settings.html',
        tz=tz,
        hours=hours,
        selected_days=selected_days,
        buffer_min=settings.buffer_min if settings else 0,
        min_notice_min=settings.min_notice_min if settings else 120,
        max_days_ahead=settings.max_days_ahead if settings else 30,
    )
