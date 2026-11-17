import os


def clerk_jwks_url() -> str:
    """URL of Clerk's JWKS, read from the environment on each call."""
    return os.environ["CLERK_JWKS_URL"]
