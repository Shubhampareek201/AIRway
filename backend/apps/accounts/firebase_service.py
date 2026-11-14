
import os

import firebase_admin
from firebase_admin import auth, credentials


def get_firebase_app():
    """Return the shared Firebase Admin app, initializing it once when needed."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        credentials_path = os.environ.get("FIREBASE_CREDENTIALS_PATH")
        if not credentials_path:
            raise RuntimeError("FIREBASE_CREDENTIALS_PATH is not configured.")
        cred = credentials.Certificate(credentials_path)
        return firebase_admin.initialize_app(cred)


def verify_firebase_token(id_token):
    if not id_token:
        raise ValueError("Firebase ID token is required.")

    get_firebase_app()
    return auth.verify_id_token(
        id_token,
        check_revoked=True,
    )
