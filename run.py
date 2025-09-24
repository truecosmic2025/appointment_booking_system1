import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    use_https = os.getenv("HTTPS", "0") == "1"
    if use_https:
        # Ad-hoc self-signed certificate for local HTTPS
        app.run(debug=True, ssl_context="adhoc")
    else:
        app.run(debug=True)
