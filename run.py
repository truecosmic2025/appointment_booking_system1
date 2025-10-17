import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    use_https = os.getenv("HTTPS", "0") == "1"
    debug = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes")
    use_reloader = os.getenv("RELOAD", "0").lower() in ("1", "true", "yes")
    if use_https:
        # Ad-hoc self-signed certificate for local HTTPS
        app.run(debug=debug, use_reloader=use_reloader, ssl_context="adhoc")
    else:
        app.run(debug=debug, use_reloader=use_reloader)
