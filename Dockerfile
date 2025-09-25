# syntax=docker/dockerfile:1

# Minimal, production-oriented image for TrueCosmic Calendar (Flask)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install tzdata so time zone logic works properly
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# Copy the rest of the application
COPY . .

# Expose HTTP port (use 8000 by convention for app servers)
EXPOSE 8000

# Environment configuration
# - SECRET_KEY, DATABASE_URL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SMTP_* etc. can be injected at runtime
# - By default, the app uses SQLite at app/app.db inside the image

# Run with Gunicorn in production mode
# Bind to the port provided by the platform (e.g., Railway sets $PORT)
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-8000} run:app"]
