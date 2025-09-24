Role: You're a very senior experienced full stack developer and architect.

Task: Create an appointment booking system closely mimicking Calendly using Python Flask, HTML, CSS, Tailwind, and Vanilla JS.


# Calendly Clone Feature Overview

## Core Functionality:
- **Scheduling:** Allows users to easily book meetings.
- **Event Types:** Customizable event types (e.g., one-on-one 30 mins).
- **Availability:** Users can set their availability, connect multiple calendars, and define scheduling rules, buffers.
- **Meeting Location:** Integration with conferencing tools like  Google Meet.
- **Sharing:** Scheduling links can be shared directly, embedded in emails or websites.

## Key Features for Clone:
- **Event Type:** User specified a single event type of 30 minutes.
- **Calendar Integration:** Google Calendar integration is required.
- **Meeting Links:** Google Meet links should be generated.

## User Interface Elements (from homepage):
- Sign up with Email option.
- Display of available time slots for booking.
- Confirmation of selected time.
- Time zone selection.

## Integrations mentioned:
- Google Calendar
- Google Meet

## Workflow Automation:
- Reminders and follow-up emails/SMS.

## Admin Management:
- Tools for onboarding, consistency, tracking, security.


## Detailed Booking Flow Analysis

### Step 1: Date Selection Interface
- Clean calendar view with month navigation (left/right arrows)
- Days of the week header (SUN, MON, TUE, WED, THU, FRI, SAT)
- Available dates highlighted in blue, unavailable dates grayed out
- Selected date gets a blue background
- Time zone selector at the bottom with dropdown
- Event details shown on the left: company logo, event name, duration, description

### Step 2: Time Selection Interface
- Shows selected date prominently (e.g., "Tuesday, September 23")
- Available time slots displayed as buttons on the right side
- Selected time slot highlighted
- "Next" button to proceed to booking form

### Step 3: Booking Form Interface
- "Enter Details" header
- Back arrow to return to previous step
- Required fields marked with asterisk:
  - Name field (text input)
  - Email field (text input)
- "Add Guests" button for inviting additional attendees
- Optional text area: "Please share anything that will help prepare for our meeting"
- Meeting summary box showing:
  - Time: "11:30pm - 12:00am, Tuesday, September 23, 2025"
  - Time zone indicator: "UTC Time"
  - Event description
- Terms of Use and Privacy Notice links
- Blue "Schedule Event" button to complete booking

### Key UI/UX Patterns:
- Consistent blue color scheme (#007BFF or similar)
- Clean, minimal design with plenty of white space
- Progressive disclosure (step-by-step flow)
- Clear visual hierarchy with headings and sections
- Responsive layout that works in modal/popup format
- Consistent branding area on the left side
- Form validation and required field indicators
- Professional, trustworthy appearance

