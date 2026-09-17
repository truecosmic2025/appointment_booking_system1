# Legacy Admin Notification Path Retired

The legacy `app.py` notification path and its configurable administrator recipient list have been removed. It belonged to the older single-event application flow and was not the live multi-coach notification source.

Multi-coach booking notices are now defined by [Unified Booking Notifications](UnifiedBookingNotifications.md). The calendar application remains the only booking-email sender and sends individual internal notices to the booked coach, `admin@truecosmic.com`, and `info@truecosmic.com`. It appends a bounded Claudde conversation summary only to internal messages when the CRM returns one unique, recent completed context match.
