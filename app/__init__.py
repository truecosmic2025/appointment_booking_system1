from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
import click
from dotenv import load_dotenv

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app():
    # Load .env if present to simplify local setup
    load_dotenv()
    app = Flask(__name__)

    # Basic config (override via env in production)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", f"sqlite:///{os.path.join(app.root_path, 'app.db')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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
    from .dashboard.routes import dash_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(google_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(dash_bp)

    # Create tables if not exist
    with app.app_context():
        db.create_all()

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
