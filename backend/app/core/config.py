import os


def clerk_jwks_url() -> str:
    """URL of Clerk's JWKS, read from the environment on each call."""
    return os.environ["CLERK_JWKS_URL"]


def clerk_issuer() -> str:
    """Expected `iss` of Clerk session tokens, read from the environment on each call."""
    return os.environ["CLERK_ISSUER"]


def clerk_authorized_parties() -> list[str]:
    """Allowed `azp` values from comma-separated CLERK_AUTHORIZED_PARTIES; empty means any."""
    raw = os.environ.get("CLERK_AUTHORIZED_PARTIES", "")
    return [party.strip() for party in raw.split(",") if party.strip()]


def database_url() -> str:
    """SQLAlchemy URL of the app database, read from the environment on each call."""
    return os.environ["DATABASE_URL"]


def cors_allowed_origins() -> list[str]:
    """Browser origins allowed to call the API, from comma-separated CORS_ALLOWED_ORIGINS."""
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
