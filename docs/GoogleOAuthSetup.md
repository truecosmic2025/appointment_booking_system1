# Google OAuth Setup (Non‑Technical, Step‑By‑Step)

This guide shows exactly how to get your Google OAuth credentials (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET) and connect Google Calendar for coaches in your TrueCosmic Calendar app.

You will do three main things:
- Create a Google Cloud project
- Turn on Google Calendar API and set up the OAuth Consent Screen
- Create OAuth credentials (Client ID + Client Secret) and plug them into the app

---

## 0) What you need before starting
- A Google account you can sign in with (e.g. your Gmail).
- Your app running locally at: http://localhost:5000

The app already loads a local `.env` file if present, and reads `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` automatically.

---

## 1) Open Google Cloud Console
1. Visit: https://console.cloud.google.com
2. If asked, sign in with your Google account.
3. In the top bar, click the Project selector and choose “New Project”.
4. Give it a name like “TrueCosmic Calendar Dev”. Click “Create”.
5. Ensure this new project is selected (you’ll see its name in the top bar).

---

## 2) Enable the Google Calendar API
1. In the left sidebar, click “APIs & Services” → “Library”.
2. Search for “Google Calendar API”.
3. Click it, then click “Enable”.

That turns on the Calendar API for your project.

---

## 3) Configure the OAuth consent screen
1. In the left sidebar, go to “APIs & Services” → “OAuth consent screen”.
2. For User Type, pick “External” (simplest for testing). Click “Create”.
3. App information:
   - App name: “TrueCosmic Calendar” (or anything you like).
   - User support email: pick your email.
   - Developer contact information: add your email.
   - Click “Save and Continue”.
4. Scopes: click “Add or Remove Scopes”. Search for and add this scope:
   - https://www.googleapis.com/auth/calendar (Full access to Calendar)
   
   **Detailed steps for adding scopes:**
   - When you click "Add or Remove Scopes", you'll see a modal with two sections: "Your non-sensitive scopes" and "Your restricted scopes"
   - In the filter/search box at the top, type "calendar" to narrow down the options
   - You'll see several calendar-related scopes. Look for the one that shows:
     - Scope: `https://www.googleapis.com/auth/calendar`
     - Description: "See, edit, share, and permanently delete all the calendars you can access using Google Calendar"
   - Check the box next to this scope to select it
   - It will move to the "Your restricted scopes" section on the right
   - This scope allows your app to read calendar availability and create/modify events with Google Meet links
   - Click “Update”, then “Save and Continue”.
5. Test users (only needed while the app is in testing):
   - Click “Add users”, enter the Google emails that will test this (your own and your coaches’ Gmail accounts).
   - Click “Save and Continue”, and finally “Back to Dashboard”.

Tip: While in testing, only the added test users can complete OAuth. Later, if you publish the app to Production, anyone can authorize.

---

## 4) Create OAuth client credentials (Client ID & Secret)
1. In the left sidebar, go to “APIs & Services” → “Credentials”.
2. Click “+ Create Credentials” → “OAuth client ID”.
3. Application type: choose “Web application”.
4. Name: “TrueCosmic Calendar Local”.
5. Authorized JavaScript origins:
   - Add: `http://localhost:5000`
6. Authorized redirect URIs (VERY IMPORTANT):
   - Add: `http://localhost:5000/google/callback`
7. Click “Create”.
8. A popup will show your Client ID and Client Secret. Keep this window open or copy them somewhere safe.

---

## 5) Put the credentials into the app
Use one of these two methods (pick the easiest for you):

A) Use a `.env` file (recommended)
- In your project folder (where `run.py` is), create a file named `.env` with exactly these lines:

```
GOOGLE_CLIENT_ID=your_client_id_here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret_here
```

- Save the file. Our app automatically loads `.env` on startup.

B) Set environment variables for just this PowerShell window
- In PowerShell (from your project folder), run:

```
$env:GOOGLE_CLIENT_ID = "your_client_id_here.apps.googleusercontent.com"
$env:GOOGLE_CLIENT_SECRET = "your_client_secret_here"
```

These variables stay set until you close that PowerShell window.

---

## 6) Connect Google Calendar in the app
1. Start the app (in PowerShell inside your project folder):

```
.\\.venv\Scripts\Activate.ps1
python run.py
```

2. Open http://localhost:5000 in your browser.
3. Register or sign in as a Coach (Host) or Owner/Admin.
4. Go to “Account” (top right) → click “Connect Google Calendar”.
5. You’ll see Google’s consent screen. Log in (use a Test User if still in testing). Approve the requested permissions.
6. If successful, you’ll be redirected back and see a “Google Calendar connected” message.

Now your booking pages can read your availability and create Calendar events with Google Meet links.

---

## 7) Try a real booking
1. Go to “Coaches” in the navigation.
2. Click your coach card to open `/c/<your-slug>`.
3. Pick a date and time slot (30 minutes) and enter name + email.
4. Book. You should receive a Google Calendar invite with a Google Meet link. The coach (you) will get it too. The Owner/Admin is also added as an attendee.

---

## Common Issues & Fixes
- Redirect URI mismatch
  - Make sure the Authorized redirect URI in Google matches EXACTLY: `http://localhost:5000/google/callback`
  - If your app runs on a different port or domain, add that exact callback URL in Google Cloud → Credentials → your OAuth client → Edit.

- “This app isn’t verified” warning
  - That’s normal while in testing. Click “Advanced” → “Continue”. For team testing, ensure all testers are added under Test Users on the consent screen.

- “Error 403: access_denied” for someone
  - Add their Google email under Test Users (Consent screen) or publish the app to Production later.

- Emails not arriving
  - The app can send emails if SMTP is configured. Set these in `.env` (optional):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
MAIL_FROM="TrueCosmic Calendar <your_email@gmail.com>"
```

  - For Gmail, you likely need to create an App Password (in Google Account → Security) if 2‑step verification is on.

- Availability shows no slots
  - Confirm the coach successfully connected Google Calendar.
  - Try a workday between 09:00–17:00 UTC (the MVP uses these hours).
  - Create a test event in your Google Calendar and refresh to see if free/busy changes.

---

## What to change for production later
- Use your real domain (e.g., `https://calendar.yourcompany.com`) and add it to Authorized Origins and Redirect URIs.
- On the OAuth consent screen, set Publishing status to “In production”. You will need to provide a homepage and privacy policy links.
- Store Google credentials securely (the app stores them in the DB for now; you can add encryption at rest).

---

## Need help?
If you get stuck, share the exact error message or a screenshot; I’ll point you to the exact step to fix.

