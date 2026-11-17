import os


def clerk_jwks_url() -> str:
    """URL of Clerk's JWKS, read from the environment on each call."""
    return os.environ["CLERK_JWKS_URL"]


def database_url() -> str:
    """SQLAlchemy URL of the app database, read from the environment on each call."""
    return os.environ["DATABASE_URL"]
