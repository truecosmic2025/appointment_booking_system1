"""
Migration script to add timezone field to User model and sync from CoachProfile.
Run this after updating the code to add the timezone field to User model.

Usage: python migrate_user_timezone.py
"""

from app import create_app, db
from app.models.user import User
from app.models.coach_profile import CoachProfile
from sqlalchemy import text

def migrate_timezones():
    app = create_app()
    with app.app_context():
        print("Starting timezone migration...")
        
        # Step 1: Add timezone column to user table if it doesn't exist
        print("\nStep 1: Adding timezone column to user table...")
        try:
            # Check if column exists
            result = db.session.execute(text("PRAGMA table_info(user)"))
            columns = [row[1] for row in result]
            
            if 'timezone' not in columns:
                print("Adding timezone column...")
                db.session.execute(text("ALTER TABLE user ADD COLUMN timezone VARCHAR(64) DEFAULT 'UTC' NOT NULL"))
                db.session.commit()
                print("✓ Timezone column added successfully")
            else:
                print("✓ Timezone column already exists")
        except Exception as e:
            print(f"✗ Error adding column: {e}")
            db.session.rollback()
            return
        
        # Step 2: Sync timezones from CoachProfile to User
        print("\nStep 2: Syncing timezones from CoachProfile to User...")
        try:
            # Get all users
            users = User.query.all()
            updated_count = 0
            
            for user in users:
                # Check if user has a coach profile with timezone
                profile = CoachProfile.query.filter_by(user_id=user.id).first()
                
                if profile and profile.timezone:
                    # Sync timezone from CoachProfile to User
                    if not user.timezone or user.timezone == 'UTC':
                        user.timezone = profile.timezone
                        updated_count += 1
                        print(f"  Updated {user.email} timezone to {profile.timezone}")
                elif not user.timezone:
                    # Set default timezone if not set
                    user.timezone = 'UTC'
                    print(f"  Set default UTC timezone for {user.email}")
            
            # Commit all changes
            db.session.commit()
            print(f"\n✓ Migration complete! Updated {updated_count} users with timezone from their coach profiles.")
            print(f"✓ Total users processed: {len(users)}")
        except Exception as e:
            print(f"✗ Error syncing timezones: {e}")
            db.session.rollback()
            return
        
        print("\n" + "="*60)
        print("Migration completed successfully!")
        print("="*60)

if __name__ == '__main__':
    migrate_timezones()