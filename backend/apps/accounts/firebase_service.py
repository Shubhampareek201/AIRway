
import os

import firebase_admin
from firebase_admin import auth, credentials


def verify_firebase_token(id_token):
    if not id_token:
        raise ValueError("Firebase ID token is required.")

    try:
        firebase_admin.get_app()
    except ValueError:
        credentials_path = os.environ.get(
            "FIREBASE_CREDENTIALS_PATH"
        )

        if not credentials_path:
            raise RuntimeError(
                "FIREBASE_CREDENTIALS_PATH is not configured."
            )

        cred = credentials.Certificate(credentials_path)
        firebase_admin.initialize_app(cred)

    return auth.verify_id_token(
        id_token,
        check_revoked=True,
    )
