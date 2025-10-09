# Timezone Implementation Guide

## Overview

The appointment booking system now displays all dates and times in the timezone of the currently logged-in user throughout the application. This ensures consistency and prevents confusion when users are in different timezones.

## Key Features

### 1. User Timezone Storage
- **User Model**: Each user now has a `timezone` field (default: 'UTC')
- **CoachProfile Model**: Maintains its own `timezone` field for backward compatibility
- **Priority**: User timezone takes precedence over CoachProfile timezone

### 2. Timezone Display Locations

#### Dashboard Views
- **Host Dashboard** (`/dashboard/host`): Shows upcoming sessions in the host's timezone
- **Owner Dashboard** (`/dashboard/owner`): Shows all sessions in the owner/admin's timezone
- Both dashboards display current time in the user's timezone with live updates

#### Booking Management
- **Manage Booking Page** (`/booking/<id>/<token>`): Shows booking time in visitor's timezone
- **Reschedule Slots**: Available time slots are displayed in visitor's timezone

#### Public Booking Page
- **Coach Booking Page** (`/c/<slug>`): Allows visitors to select their timezone
- Time slots are dynamically converted to the selected timezone
- Timezone preference is stored in browser localStorage

### 3. Email Notifications

All email notifications send times in the recipient's timezone:

- **Booking Confirmation**: Each recipient (coach, visitor, owner, admins) receives the email with times in their timezone
- **Cancellation Notification**: Times shown in each recipient's timezone
- **Reschedule Notification**: New time shown in each recipient's timezone

Recipients include:
- Coach (uses User.timezone or CoachProfile.timezone)
- Visitor (uses Booking.timezone - the timezone they selected during booking)
- Owner (uses User.timezone)
- Admin emails from ADMIN_EMAILS env var (uses User.timezone if they have an account)

## Implementation Details

### Helper Functions

#### `_current_tz_name()` in `app/__init__.py`
Returns the timezone for the currently logged-in user:
1. Checks `current_user.timezone` first
2. Falls back to `CoachProfile.timezone` if available
3. Defaults to 'UTC'

#### `_tz_for_user_email(email)` in `app/coach/public.py`
Returns timezone for a user by email:
1. Looks up user by email
2. Checks `User.timezone` first
3. Falls back to `CoachProfile.timezone`
4. Returns None if user not found

#### `_format_dt_for_tz(dt, tzname)` in `app/coach/public.py`
Formats a datetime in a specific timezone:
- Converts UTC datetime to specified timezone
- Returns formatted string and timezone name used
- Handles errors gracefully with fallbacks

### Jinja2 Filters

#### `dt_local` Filter
Template filter that converts UTC datetime to user's local timezone:
```jinja
{{ booking.start_utc|dt_local }}
```

### Context Processors

#### `current_tz_name`
Available in all templates to show the current user's timezone:
```jinja
Current time ({{ current_tz_name }}): {{ now|dt_local }}
```

## Database Schema Changes

### User Model
```python
class User(UserMixin, db.Model):
    # ... existing fields ...
    timezone = db.Column(db.String(64), default='UTC', nullable=False)
```

## Migration

### For Existing Installations

1. **Update the code** with the new timezone implementation

2. **Run the migration script**:
   ```bash
   python migrate_user_timezone.py
   ```
   
   This script will:
   - Add the timezone field to existing User records
   - Sync timezones from CoachProfile to User where applicable
   - Set 'UTC' as default for users without a timezone

3. **Restart the application**

### For New Installations

The timezone field will be automatically created when the database is initialized.

## User Experience

### For Coaches/Hosts
- Set your timezone in your profile settings
- Dashboard shows all times in your timezone
- Email notifications use your timezone

### For Visitors/Attendees
- Select your timezone when booking
- Manage booking page shows times in your timezone
- Email confirmations use your timezone

### For Owners/Admins
- Set your timezone in your profile
- Dashboard shows all bookings in your timezone
- Email notifications use your timezone

## Timezone Selection

The system supports all IANA timezone identifiers, including:
- `America/New_York`
- `Europe/London`
- `Asia/Kolkata`
- `Asia/Tokyo`
- `Australia/Sydney`
- And many more...

## Technical Notes

### Storage Format
- All datetimes are stored in UTC in the database
- Conversion to local timezone happens at display time
- This ensures consistency and prevents timezone-related bugs

### Browser Detection
- The booking page auto-detects the visitor's timezone using JavaScript
- Visitors can override this by selecting a different timezone
- Selection is saved in localStorage for convenience

### Error Handling
- If timezone conversion fails, the system falls back to UTC
- Invalid timezone names are handled gracefully
- All timezone operations are wrapped in try-catch blocks

## Testing Recommendations

1. **Test with different user timezones**:
   - Create users in different timezones
   - Verify dashboard displays correct local times
   - Check email notifications show correct times

2. **Test booking flow**:
   - Book sessions from different timezones
   - Verify available slots are correct
   - Check confirmation emails

3. **Test edge cases**:
   - Daylight saving time transitions
   - Bookings across date boundaries
   - Invalid timezone handling

## Troubleshooting

### Times showing in UTC instead of local timezone
- Check that user has timezone set in their profile
- Verify pytz is installed: `pip install pytz`
- Check browser console for JavaScript errors

### Email notifications showing wrong times
- Verify SMTP settings are correct
- Check that EMAIL_ENABLED=true in environment
- Ensure recipient users have timezone set

### Booking slots not appearing
- Check coach's working hours are set
- Verify Google Calendar is connected
- Check min_notice and max_days_ahead settings

## Future Enhancements

Potential improvements for timezone handling:
- Add timezone selector in user profile settings UI
- Show multiple timezones simultaneously in dashboard
- Add timezone abbreviations (EST, PST, etc.) alongside full names
- Implement automatic timezone detection on login
- Add timezone conversion tooltips on hover