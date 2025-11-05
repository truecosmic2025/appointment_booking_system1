from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
import click
import logging
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app():
    # Load .env if present to simplify local setup
    load_dotenv()
    app = Flask(__name__)

    # Basic config (override via env in production)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    # Use DATABASE_URL if provided (Railway Postgres), else fallback to SQLite.
    db_uri = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(app.root_path, 'app.db')}")
    # Normalize legacy postgres:// URIs to postgresql:// for SQLAlchemy
    if db_uri.startswith("postgres://"):
        db_uri = db_uri.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Configure root logging once so integration modules log visibly
    try:
        log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_name, logging.INFO)
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            handler.setFormatter(formatter)
            root_logger.addHandler(handler)
        root_logger.setLevel(log_level)
    except Exception:
        pass

    # Trust reverse proxy headers (Railway/Heroku-style) for scheme/host
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Models import for SQLAlchemy configuration
    from .models.user import User  # noqa: F401

    # Blueprints
    from .routes import main_bp
    from .auth.routes import auth_bp
    from .admin.routes import admin_bp
    from .google.routes import google_bp
    from .coach.public import public_bp
    from .coach.settings_routes import coach_bp
    from .dashboard.routes import dash_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(google_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(dash_bp)
    app.register_blueprint(coach_bp)

    # Optional per-request timezone override via query param (?tz=UTC or ?tz=local)
    @app.before_request
    def _tz_override():
        try:
            tz = (request.args.get('tz') or '').strip()
            if tz.upper() == 'UTC':
                g._tz_override = 'UTC'
            elif tz.lower() == 'local' or tz == '':
                g._tz_override = None
        except Exception:
            g._tz_override = None

    # Jinja helpers: current timezone and local dt formatting
    def _current_tz_name():
        try:
            from flask_login import current_user
            from .models.coach_profile import CoachProfile
            # Per-request override (e.g., tz=UTC)
            if getattr(g, '_tz_override', None):
                return g._tz_override
            if getattr(current_user, 'is_authenticated', False):
                # First check User timezone, then fall back to CoachProfile
                if hasattr(current_user, 'timezone') and current_user.timezone:
                    return current_user.timezone
                prof = CoachProfile.query.filter_by(user_id=current_user.id).first()
                if prof and prof.timezone:
                    return prof.timezone
        except Exception:
            pass
        return 'UTC'

    def dt_local(dt, fmt='%Y-%m-%d %H:%M'):
        try:
            import pytz
            tzname = _current_tz_name()
            tz = pytz.timezone(tzname)
            # Ensure aware UTC first
            aware = dt
            if getattr(dt, 'tzinfo', None) is None:
                aware = dt.replace(tzinfo=pytz.UTC)
            local = aware.astimezone(tz)
            return local.strftime(fmt)
        except Exception:
            try:
                return dt.strftime(fmt)
            except Exception:
                return str(dt)

    app.jinja_env.filters['dt_local'] = dt_local

    @app.context_processor
    def inject_tz():
        return {
            'current_tz_name': _current_tz_name(),
        }

    # Create tables if not exist and run migrations
    with app.app_context():
        db.create_all()
        
        # Auto-migrate: Add timezone column to user table if it doesn't exist
        try:
            from sqlalchemy import text, inspect
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('user')]
            
            if 'timezone' not in columns:
                print("Running timezone migration: Adding timezone column to user table...")
                db.session.execute(text("ALTER TABLE user ADD COLUMN timezone VARCHAR(64) DEFAULT 'UTC' NOT NULL"))
                db.session.commit()
                print("✓ Timezone column added successfully")
                
                # Sync timezones from CoachProfile to User
                from .models.user import User
                from .models.coach_profile import CoachProfile
                
                users = User.query.all()
                updated_count = 0
                
                for user in users:
                    profile = CoachProfile.query.filter_by(user_id=user.id).first()
                    if profile and profile.timezone and (not user.timezone or user.timezone == 'UTC'):
                        user.timezone = profile.timezone
                        updated_count += 1
                
                if updated_count > 0:
                    db.session.commit()
                    print(f"✓ Synced {updated_count} user timezones from CoachProfile")
            
            # Auto-migrate: Add is_active column to user table if it doesn't exist
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('user')]
            if 'is_active' not in columns:
                try:
                    print("Running migration: Adding is_active column to user table...")
                    # SQLite uses INTEGER for booleans; default to 1 (true)
                    db.session.execute(text("ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL"))
                    db.session.commit()
                    print("✓ is_active column added successfully")
                except Exception as _e:
                    # If migration fails (e.g., other DB), ignore silently to avoid crash
                    db.session.rollback()
                    pass
            booking_columns = [col['name'] for col in inspector.get_columns('booking')]
            if 'visitor_phone' not in booking_columns:
                try:
                    print("Running migration: Adding visitor_phone column to booking table...")
                    db.session.execute(text("ALTER TABLE booking ADD COLUMN visitor_phone VARCHAR(32)"))
                    db.session.commit()
                    print("visitor_phone column added successfully")
                except Exception as _e:
                    db.session.rollback()
                    pass
        except Exception as e:
            # Migration already done or error - continue silently
            pass

    # CLI helpers
    @app.cli.command("create-user")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--role", type=click.Choice(["owner", "admin", "host", "invitee"]), default="host")
    def create_user(email, name, password, role):
        """Create a user account."""
        from .models.user import User
        from .models.coach_profile import CoachProfile

        if User.query.filter_by(email=email.lower()).first():
            click.echo("User already exists")
            return
        user = User(email=email.lower().strip(), name=name.strip(), role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        if role in ("host", "owner", "admin"):
            slug = CoachProfile.generate_slug(name)
            prof = CoachProfile(user_id=user.id, slug=slug)
            db.session.add(prof)
            db.session.commit()
        click.echo(f"Created {role} user: {email}")

    @app.cli.command("purge-users")
    @click.option("--force", is_flag=True, help="Skip confirmation")
    def purge_users(force: bool):
        """Delete ALL users, coach profiles, and bookings."""
        from .models import User, CoachProfile, Booking

        if not force:
            click.confirm(
                "This will DELETE all users, coach profiles, and bookings. Continue?",
                abort=True,
            )
        b = db.session.query(Booking).delete(synchronize_session=False)
        p = db.session.query(CoachProfile).delete(synchronize_session=False)
        u = db.session.query(User).delete(synchronize_session=False)
        db.session.commit()
        click.echo(f"Deleted: users={u}, coach_profiles={p}, bookings={b}")

    return app
