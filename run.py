import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes")
    use_reloader = os.getenv("RELOAD", "0").lower() in ("1", "true", "yes")

    # Bind host/port (override with HOST/PORT)
    host = os.getenv("HOST", "127.0.0.1")
    try:
        port = int(os.getenv("PORT", "5000"))
    except ValueError:
        port = 5000

    # Decide HTTPS behavior
    https_env = (os.getenv("HTTPS") or "auto").lower()
    cert_file = os.getenv("SSL_CERT_FILE") or os.getenv("SSL_CERT")
    key_file = os.getenv("SSL_KEY_FILE") or os.getenv("SSL_KEY")
    have_real_cert = bool(
        cert_file and key_file and os.path.exists(cert_file) and os.path.exists(key_file)
    )

    if https_env in ("1", "true", "yes"):
        # Explicitly requested HTTPS; use real cert if present, otherwise adhoc
        ssl_ctx = (cert_file, key_file) if have_real_cert else "adhoc"
        app.run(host=host, port=port, debug=debug, use_reloader=use_reloader, ssl_context=ssl_ctx)
    elif https_env in ("0", "false", "no"):
        # Explicitly requested HTTP
        app.run(host=host, port=port, debug=debug, use_reloader=use_reloader)
    else:
        # auto: use HTTPS only if a real cert is provided; otherwise HTTP
        if have_real_cert:
            app.run(host=host, port=port, debug=debug, use_reloader=use_reloader, ssl_context=(cert_file, key_file))
        else:
            app.run(host=host, port=port, debug=debug, use_reloader=use_reloader)
